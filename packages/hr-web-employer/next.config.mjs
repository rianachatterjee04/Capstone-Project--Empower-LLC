// PERMISSIONS-POLICY AND THE CAMERA.
// This header used to read `camera=(), microphone=()`, an EMPTY allowlist,
// which denies the feature to every origin including this one. The product's
// flagship screen asks the candidate for their camera and microphone through
// getUserMedia; under that header the browser refuses before the permission
// prompt is ever shown, and the failure looks exactly like a candidate
// clicking "block".
//
// `self` is the correct value: this origin may ask, and an embedded
// third-party frame still may not. Geolocation stays fully denied because
// nothing here asks for it.
const securityHeaders = [
  { key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains; preload' },
  { key: 'X-Frame-Options', value: 'DENY' },
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  { key: 'Permissions-Policy', value: 'camera=(self), microphone=(self), geolocation=()' },
  { key: 'Content-Security-Policy', value: "frame-ancestors 'none'; base-uri 'self'; object-src 'none'" },
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  basePath: '/people',

  // A build here must not destroy a running dev server's .next directory.
  // That happened once: `npm run build` overwrote the chunks the dev server
  // was serving, and the app in the browser broke with no code change to
  // explain it.
  distDir: process.env.NEXT_DIST_DIR || '.next',

  // Inherited app: don't fail production builds on pre-existing lint nits
  // (still lint in dev/CI).
  eslint: { ignoreDuringBuilds: true },

  // THE COMMENT HERE USED TO SAY "Type errors still block the build" WHILE
  // THE SETTING SAID `ignoreBuildErrors: true`. It did the opposite of what
  // it claimed, which is how six type errors accumulated in pages nobody had
  // touched. `tsc --noEmit` is clean, so the guard can be real now.
  typescript: { ignoreBuildErrors: false },

  async headers() {
    return [{ source: '/:path*', headers: securityHeaders }];
  },
};
export default nextConfig;
