import { NextResponse } from "next/server";
import { fetchYearTotals } from "@/lib/economic";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ year: string }> }
) {
  try {
    const { year } = await params;
    const data = await fetchYearTotals(year);
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 });
  }
}
