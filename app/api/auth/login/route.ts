import { NextResponse } from "next/server";
import bcrypt from "bcryptjs";
import { signToken, COOKIE } from "@/lib/auth";

export async function POST(req: Request) {
  try {
    const { password } = await req.json();

    if (typeof password !== "string" || password.length === 0) {
      return NextResponse.json({ error: "Ugyldigt input" }, { status: 400 });
    }

    const hash = process.env.AUTH_PASSWORD_HASH!;
    const valid = await bcrypt.compare(password, hash);

    if (!valid) {
      return NextResponse.json({ error: "Forkert adgangskode" }, { status: 401 });
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
  } catch {
    return NextResponse.json({ error: "Intern serverfejl" }, { status: 500 });
  }
}
