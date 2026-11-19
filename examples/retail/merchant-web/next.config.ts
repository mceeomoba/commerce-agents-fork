// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import type { NextConfig } from "next";

const staticExport = process.env.STATIC_EXPORT === "1";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // STATIC_EXPORT=1 emits plain files (out/) for a host without Node. The Python API serves them
  // under /merchant/ on the same origin as the storefront.
  ...(staticExport ? { output: "export" as const, trailingSlash: true, basePath: "/merchant" } : {}),
  transpilePackages: ["web-shared"],
};

export default nextConfig;
