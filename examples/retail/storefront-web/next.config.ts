// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import type { NextConfig } from "next";

const staticExport = process.env.STATIC_EXPORT === "1";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // STATIC_EXPORT=1 emits plain files (out/) for a host without Node; the Python API serves them.
  ...(staticExport ? { output: "export" as const, trailingSlash: true } : {}),
  transpilePackages: ["web-shared"],
  // Single-origin hosting: with API_PROXY_TARGET set, /api/* is proxied to the Python API.
  async rewrites() {
    const target = process.env.API_PROXY_TARGET;
    return target && !staticExport ? [{ source: "/api/:path*", destination: `${target}/api/:path*` }] : [];
  },
};

export default nextConfig;
