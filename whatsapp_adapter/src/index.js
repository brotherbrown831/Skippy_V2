/**
 * Skippy WhatsApp Adapter
 *
 * Bridges WhatsApp (via Baileys multidevice protocol) to Skippy's HTTP API.
 * Runs as a standalone Docker container.
 *
 * First-run: scan QR code from docker compose logs whatsapp_adapter
 * Reconnect automatically using persisted session from Docker volume
 */

import makeWASocket, {
  DisconnectReason,
  fetchLatestBaileysVersion,
  useMultiFileAuthState,
} from "@whiskeysockets/baileys";
import { Boom } from "@hapi/boom";
import qrcode from "qrcode-terminal";
import pino from "pino";
import { existsSync, mkdirSync } from "fs";
import { join } from "path";

// --- Configuration (from environment) ---

const SKIPPY_BASE_URL = process.env.SKIPPY_BASE_URL || "http://skippy:8000";
const SESSION_PATH = process.env.WHATSAPP_SESSION_PATH || "/app/sessions";
const ALLOWED_NUMBERS_RAW = process.env.WHATSAPP_ALLOWED_NUMBERS || "";
const ALLOW_GROUPS = process.env.WHATSAPP_ALLOW_GROUPS === "true";
const REQUEST_TIMEOUT_MS = parseInt(process.env.SKIPPY_TIMEOUT_MS || "30000", 10);
const LOG_LEVEL = process.env.LOG_LEVEL || "info";

// --- Parse whitelist (comma-separated phone numbers) ---

function parseAllowedNumbers(raw) {
  if (!raw.trim()) return null; // null = allow all
  return new Set(
    raw
      .split(",")
      .map((n) => n.trim().replace(/[^0-9]/g, "")) // strip non-digits
      .filter(Boolean)
      .map((n) => `${n}@s.whatsapp.net`) // Baileys JID format: <number>@s.whatsapp.net
  );
}

const ALLOWED_JIDS = parseAllowedNumbers(ALLOWED_NUMBERS_RAW);

// --- Logger ---

const logger = pino({
  level: LOG_LEVEL,
  timestamp: pino.stdTimeFunctions.isoTime,
  transport: {
    target: "pino-pretty",
    options: { colorize: false, translateTime: "SYS:standard" },
  },
}).child({ service: "whatsapp-adapter" });

// Baileys uses pino internally; silence it to warn level
const baileysLogger = pino({ level: "warn" });

// --- Ensure session directory exists ---

if (!existsSync(SESSION_PATH)) {
  mkdirSync(SESSION_PATH, { recursive: true });
  logger.info({ sessionPath: SESSION_PATH }, "Created session directory");
}

// --- Reconnection state (Fix 2: backoff with jitter) ---

let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 10;

function backoffDelay(attempt) {
  // Exponential backoff: 2s → 4s → 8s → ... capped at 60s
  const base = Math.min(2000 * Math.pow(2, attempt), 60_000);
  // ±20% jitter prevents thundering herd if WhatsApp drops many connections at once
  const jitter = base * 0.2 * (Math.random() * 2 - 1);
  return Math.round(base + jitter);
}

// --- Fix 5: Startup probe for Skippy health ---

async function waitForSkippy(maxAttempts = 10, delayMs = 3000) {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const res = await fetch(`${SKIPPY_BASE_URL}/health`, {
        signal: AbortSignal.timeout(5000),
      });
      if (res.ok) {
        logger.info("Skippy API is reachable");
        return;
      }
    } catch (err) {
      // not ready yet
    }
    logger.warn(
      { attempt: i + 1, maxAttempts },
      "Waiting for Skippy to be ready..."
    );
    await new Promise((r) => setTimeout(r, delayMs));
  }
  logger.warn(
    "Skippy not reachable at startup — will retry on first message"
  );
  // Don't exit; individual requests will fail gracefully with error messages
}

// --- Core: Send message to Skippy and return response text ---

async function querySkippy(messageText, chatId) {
  const payload = {
    text: messageText,
    conversation_id: `whatsapp:${chatId}`,
    language: "en",
    agent_id: "skippy",
    source: "whatsapp",
  };

  const controller = new AbortController();
  const timeoutHandle = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(`${SKIPPY_BASE_URL}/webhook/skippy`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`Skippy returned HTTP ${response.status}`);
    }

    const data = await response.json();
    // VoiceResponse has both 'response' and 'response_text' — prefer response_text
    return (
      data.response_text ||
      data.response ||
      "I got your message but had nothing to say."
    );
  } catch (err) {
    if (err.name === "AbortError") {
      logger.error({ chatId }, "Skippy request timed out");
      return "Sorry, I timed out trying to think about that. Try again?";
    }
    logger.error({ chatId, error: err.message }, "Skippy request failed");
    return "Sorry, I hit an error. Skippy might be down or misconfigured.";
  } finally {
    clearTimeout(timeoutHandle);
  }
}

// --- Fix 3: Extract text from message (only plain text) ---

function extractText(message) {
  // Accepted message types: plain conversation text, extended text, ephemeral text
  const body =
    message.message?.conversation ||
    message.message?.extendedTextMessage?.text ||
    message.message?.ephemeralMessage?.message?.conversation ||
    null;
  return body?.trim() || null; // null = not a plain-text message
}

// --- Fix 4: Handle message with guaranteed typing indicator cleanup ---

async function handleMessage(sock, message) {
  // Fix 3: Extract text, skip non-text messages
  const text = extractText(message);
  if (!text) {
    // Log message type for debugging (e.g., "imageMessage", "audioMessage")
    const msgType = Object.keys(message.message || {})[0] || "unknown";
    logger.debug({ msgType }, "Skipping non-text message");
    return;
  }

  // Ignore messages sent by this bot itself (avoid reply loops)
  if (message.key.fromMe) {
    logger.debug("Skipping self-sent message");
    return;
  }

  const remoteJid = message.key.remoteJid;

  // Group chat handling
  const isGroup = remoteJid.endsWith("@g.us");
  if (isGroup && !ALLOW_GROUPS) {
    logger.debug({ remoteJid }, "Skipping group message (groups disabled)");
    return;
  }

  // Whitelist enforcement (private chats only; groups pass if ALLOW_GROUPS=true)
  if (!isGroup && ALLOWED_JIDS !== null && !ALLOWED_JIDS.has(remoteJid)) {
    logger.warn({ remoteJid }, "Blocked message from unauthorized number");
    return;
  }

  const shortText = text.slice(0, 80);
  logger.info({ remoteJid, isGroup, text: shortText }, "Message received");

  // Show typing indicator while processing
  await sock.sendPresenceUpdate("composing", remoteJid);

  let responseText;
  try {
    // Fix 4: Try/finally guarantees typing indicator is always cleared
    responseText = await querySkippy(text, remoteJid);
  } finally {
    // ALWAYS clear typing indicator — even if querySkippy throws
    await sock.sendPresenceUpdate("paused", remoteJid).catch(() => {});
  }

  // Send response
  try {
    await sock.sendMessage(remoteJid, { text: responseText });
    logger.info(
      { remoteJid, responseLength: responseText.length },
      "Response sent"
    );
  } catch (err) {
    logger.error(
      { remoteJid, error: err.message },
      "Failed to send WhatsApp response"
    );
  }
}

// --- Core: Create and manage WhatsApp socket ---

async function createSocket() {
  // Fix 5: Wait for Skippy to be ready before connecting WhatsApp
  await waitForSkippy();

  const { state, saveCreds } = await useMultiFileAuthState(
    join(SESSION_PATH, "auth")
  );

  const { version, isLatest } = await fetchLatestBaileysVersion();
  logger.info({ version, isLatest }, "Using Baileys WA version");

  const sock = makeWASocket({
    version,
    logger: baileysLogger,
    printQRInTerminal: false, // We handle QR ourselves for structured logging
    auth: state,
    // Improves reliability: don't request full chat history on reconnect
    syncFullHistory: false,
    // Mark incoming messages as read automatically
    markOnlineOnConnect: true,
  });

  // Persist credentials whenever they update (session renewal, key generation, etc.)
  sock.ev.on("creds.update", saveCreds);

  // Connection state changes
  sock.ev.on("connection.update", async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      logger.info("QR code ready — scan with WhatsApp on your phone:");
      // Print readable ASCII QR to stdout (visible in docker compose logs)
      qrcode.generate(qr, { small: true });
      logger.info(
        "Waiting for QR scan... (run: docker compose logs -f whatsapp_adapter)"
      );
    }

    if (connection === "open") {
      reconnectAttempts = 0;
      logger.info("WhatsApp connection established");
    }

    if (connection === "close") {
      const statusCode =
        lastDisconnect?.error instanceof Boom
          ? lastDisconnect.error.output.statusCode
          : 0;

      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

      logger.warn(
        { statusCode, shouldReconnect, attempt: reconnectAttempts },
        "WhatsApp connection closed"
      );

      if (statusCode === DisconnectReason.loggedOut) {
        logger.error(
          "Session logged out. Delete session files and restart to re-authenticate."
        );
        process.exit(1); // Docker will restart unless restart: "no"
      }

      if (shouldReconnect) {
        if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
          logger.error(
            { maxAttempts: MAX_RECONNECT_ATTEMPTS },
            "Max reconnect attempts reached. Exiting."
          );
          process.exit(1);
        }
        const delay = backoffDelay(reconnectAttempts);
        reconnectAttempts++;
        logger.info({ delay, attempt: reconnectAttempts }, "Reconnecting...");
        setTimeout(createSocket, delay);
      }
    }
  });

  // Message handler
  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    // Only process new incoming messages, not history
    if (type !== "notify") return;
    for (const message of messages) {
      await handleMessage(sock, message);
    }
  });

  return sock;
}

// --- Entry point ---

logger.info(
  {
    skippyUrl: SKIPPY_BASE_URL,
    sessionPath: SESSION_PATH,
    allowGroups: ALLOW_GROUPS,
    whitelist: ALLOWED_JIDS
      ? `${ALLOWED_JIDS.size} numbers`
      : "OPEN (all allowed)",
  },
  "WhatsApp adapter starting"
);

createSocket().catch((err) => {
  logger.error({ error: err.message }, "Fatal startup error");
  process.exit(1);
});

// Graceful shutdown on SIGTERM/SIGINT
process.on("SIGTERM", () => {
  logger.info("Received SIGTERM, shutting down gracefully");
  process.exit(0);
});
process.on("SIGINT", () => {
  logger.info("Received SIGINT, shutting down gracefully");
  process.exit(0);
});
