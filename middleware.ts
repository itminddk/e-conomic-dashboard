import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { verifyToken, COOKIE } from "@/lib/auth";

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  if (pathname.startsWith("/login") || pathname.startsWith("/api/auth") || pathname.startsWith("/api/debug-db")) {
    return NextResponse.next();
  }

  const token = req.cookies.get(COOKIE)?.value;
  if (!token || !(await verifyToken(token))) {
    return NextResponse.redirect(new URL("/login", req.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|robots.txt).*)"],
};
