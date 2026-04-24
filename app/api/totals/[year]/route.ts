import { NextResponse } from "next/server";
import { fetchYearTotals } from "@/lib/economic";
import { VALID_YEAR } from "@/lib/validation";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ year: string }> }
) {
  try {
    const { year } = await params;
    if (!VALID_YEAR.test(year)) {
      return NextResponse.json({ error: "Ugyldigt år" }, { status: 400 });
    }
    const data = await fetchYearTotals(year);
    return NextResponse.json(data);
  } catch (err) {
    console.error("GET /api/totals/[year]:", err);
    return NextResponse.json({ error: "Intern serverfejl" }, { status: 500 });
  }
}
