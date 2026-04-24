import { NextResponse } from "next/server";
import pool from "@/lib/db";

export async function GET() {
  try {
    const [rows] = await pool.execute("SELECT username FROM users") as [{ username: string }[][], unknown];
    return NextResponse.json({ ok: true, users: rows.map(r => r.username), host: process.env.DB_HOST });
  } catch (err) {
    return NextResponse.json({ ok: false, error: String(err), host: process.env.DB_HOST }, { status: 500 });
  }
}
