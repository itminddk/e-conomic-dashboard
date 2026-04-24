import { NextResponse } from "next/server";
import bcrypt from "bcryptjs";
import { signToken, COOKIE } from "@/lib/auth";
import pool from "@/lib/db";

export async function POST(req: Request) {
  try {
    const { username, password } = await req.json();

    if (typeof username !== "string" || typeof password !== "string" ||
        username.length === 0 || password.length === 0) {
      return NextResponse.json({ error: "Ugyldigt input" }, { status: 400 });
    }

    const [rows] = await pool.execute(
      "SELECT password_hash FROM users WHERE username = ? LIMIT 1",
      [username]
    ) as [{ password_hash: string }[], unknown];

    const user = rows[0];
    const valid = user ? await bcrypt.compare(password, user.password_hash) : false;

    if (!valid) {
      return NextResponse.json({ error: "Forkert brugernavn eller adgangskode" }, { status: 401 });
    }

    const token = await signToken();
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
