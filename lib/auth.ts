import { SignJWT, jwtVerify } from "jose";

if (!process.env.AUTH_SECRET || process.env.AUTH_SECRET.length < 32) {
  throw new Error("AUTH_SECRET mangler eller er for kort (minimum 32 tegn)");
}

const secret = new TextEncoder().encode(process.env.AUTH_SECRET);
const COOKIE = "auth_session";
const EXPIRES_IN = 60 * 60 * 8; // 8 timer

export async function signToken(username: string) {
  return new SignJWT({ sub: username })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(`${EXPIRES_IN}s`)
    .sign(secret);
}

export async function verifyToken(token: string): Promise<string | null> {
  try {
    const { payload } = await jwtVerify(token, secret);
    return (payload.sub as string) ?? null;
  } catch {
    return null;
  }
}

export { COOKIE };
