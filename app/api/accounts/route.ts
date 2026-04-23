import { NextResponse } from "next/server";
import { fetchAccounts } from "@/lib/economic";

export async function GET() {
  try {
    const data = await fetchAccounts();
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
