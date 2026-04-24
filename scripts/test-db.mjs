import mysql from "mysql2/promise";
import { readFileSync, existsSync } from "fs";

function loadEnv() {
  const file = existsSync(".env.local") ? ".env.local" : existsSync(".env") ? ".env" : null;
  if (!file) return {};
  return Object.fromEntries(
    readFileSync(file, "utf8")
      .split("\n")
      .filter((l) => l.includes("=") && !l.startsWith("#"))
      .map((l) => l.split("=").map((s) => s.trim()))
      .map(([k, ...v]) => [k, v.join("=").replace(/^"|"$/g, "")])
  );
}

const env = { ...process.env, ...loadEnv() };

const socketPath = env.DB_SOCKET;
const config = socketPath
  ? { socketPath, user: env.DB_USER, password: env.DB_PASSWORD, database: env.DB_NAME }
  : { host: env.DB_HOST ?? "localhost", user: env.DB_USER, password: env.DB_PASSWORD, database: env.DB_NAME };

console.log(`Connecting to database '${config.database}' on ${socketPath ? `socket ${socketPath}` : `host ${config.host}`}…`);

let conn;
try {
  conn = await mysql.createConnection(config);
  const [[{ version }]] = await conn.execute("SELECT VERSION() AS version");
  const [rows] = await conn.execute("SELECT COUNT(*) AS count FROM users");
  const userCount = rows[0].count;
  console.log(`✓ Connected — MySQL ${version}`);
  console.log(`✓ Users table: ${userCount} row(s)`);
} catch (err) {
  console.error(`✗ Connection failed: ${err.message}`);
  process.exit(1);
} finally {
  await conn?.end();
}
