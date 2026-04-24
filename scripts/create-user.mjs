import bcrypt from "bcryptjs";
import mysql from "mysql2/promise";
import { readFileSync } from "fs";

// Læs .env.local
const env = Object.fromEntries(
  readFileSync(".env.local", "utf8")
    .split("\n")
    .filter((l) => l.includes("="))
    .map((l) => l.split("=").map((s) => s.trim()))
    .map(([k, ...v]) => [k, v.join("=").replace(/^"|"$/g, "")])
);

const [, , username, password] = process.argv;
if (!username || !password) {
  console.error("Brug: node scripts/create-user.mjs <brugernavn> <adgangskode>");
  process.exit(1);
}

const db = await mysql.createConnection({
  host: env.DB_HOST,
  user: env.DB_USER,
  password: env.DB_PASSWORD,
  database: env.DB_NAME,
});

await db.execute(`
  CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  )
`);

const hash = bcrypt.hashSync(password, 10);
await db.execute(
  "INSERT INTO users (username, password_hash) VALUES (?, ?) ON DUPLICATE KEY UPDATE password_hash = ?",
  [username, hash, hash]
);

console.log(`✓ Bruger '${username}' oprettet/opdateret.`);
await db.end();
