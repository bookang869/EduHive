import NextAuth from 'next-auth';
import GoogleProvider from 'next-auth/providers/google';
import { SignJWT } from 'jose';

const handler = NextAuth({
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET,
      authorization: {
        params: {
          scope: 'openid email profile https://www.googleapis.com/auth/calendar.events',
          access_type: 'offline',
          // ponytail: removed prompt:'consent' — forced re-consent every login; refresh_token now persisted in jwt callback
        },
      },
    }),
  ],
  callbacks: {
    async jwt({ token, account }) {
      if (account) {
        token.accessToken  = account.access_token;
        token.refreshToken = account.refresh_token;
        token.expiresAt    = account.expires_at;
      }
      return token;
    },
    async signIn({ profile }) {
      const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
      try {
        const res = await fetch(`${API}/users/upsert`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ google_sub: profile.sub, email: profile.email, name: profile.name }),
        });
        if (!res.ok) console.error('[auth] upsert failed:', res.status, await res.text().catch(() => ''));
      } catch (err) {
        console.error('[auth] upsert error:', err);
      }
      return true;
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.sub    = token.sub;
        session.accessToken = token.accessToken;
        const secret = new TextEncoder().encode(process.env.NEXTAUTH_SECRET);
        session.backendToken = await new SignJWT({ sub: token.sub })
          .setProtectedHeader({ alg: 'HS256' })
          .setExpirationTime('7d')
          .sign(secret);
      }
      return session;
    },
  },
});

export { handler as GET, handler as POST };
