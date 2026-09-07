/// <reference types="@cloudflare/workers-types" />

declare namespace Cloudflare {
  interface Env {
    // Database support is optional in the existing Sites scaffold.
    DB?: D1Database;
  }
}
