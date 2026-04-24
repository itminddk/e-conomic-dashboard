import { NextResponse } from "next/server";
import bcrypt from "bcryptjs";
import { signToken, COOKIE } from "@/lib/auth";
import pool from "@/lib/db";

// Prevents username enumeration via timing: bcrypt runs even when user doesn't exist
const DUMMY_HASH = bcrypt.hashSync("_timing_guard_", 10);

export async function POST(req: Request) {
  try {
    const { username, password } = await req.json();

    if (typeof username !== "string" || typeof password !== "string" ||
        username.length === 0 || username.length > 100 ||
        password.length === 0 || password.length > 200) {
      return NextResponse.json({ error: "Ugyldigt input" }, { status: 400 });
    }

    const [rows] = await pool.execute(
      "SELECT password_hash FROM users WHERE username = ? LIMIT 1",
      [username]
    ) as [{ password_hash: string }[], unknown];

    const user = rows[0];
    const hashToCheck = user?.password_hash ?? DUMMY_HASH;
    const hashMatches = await bcrypt.compare(password, hashToCheck);
    const valid = hashMatches && !!user;

    if (!valid) {
      return NextResponse.json({ error: "Forkert brugernavn eller adgangskode" }, { status: 401 });
    }

    const token = await signToken(username);
    const res = NextResponse.json({ ok: true });
    res.cookies.set(COOKIE, token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      maxAge: 60 * 60 * 8,
      path: "/",
    });
    return res;
  } catch (err) {
    console.error("Login fejl:", err);
    return NextResponse.json({ error: "Intern serverfejl" }, { status: 500 });
  }
}
