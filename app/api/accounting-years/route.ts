import { NextResponse } from "next/server";
import { fetchAccountingYears } from "@/lib/economic";

export async function GET() {
  try {
    const data = await fetchAccountingYears();
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
