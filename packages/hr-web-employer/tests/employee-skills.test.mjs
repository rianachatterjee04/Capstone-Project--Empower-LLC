/**
 * The Employee skills page and the server agree, and the page only calls
 * routes that exist.
 *
 * WHY THIS IS A TEST
 * The level scale (1 to 4) lives in two languages. The page offers the levels
 * and the server checks them. If one changes alone, a person picks a level the
 * page offers and the server refuses it. A type check cannot see that.
 *
 * Run with:  npm run test:ui
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { readCode } from "./_source.mjs";

const PAGE = "src/app/app/employee-skills/page.tsx";
const NAV = "src/components/nav-config.ts";
const SERVER = "../hr-api/app/services/skills_management_service.py";
const ROUTER = "../hr-api/app/api/routers/skills_management.py";

function pageNumber(name) {
  const m = readCode(PAGE).match(new RegExp(`const ${name}\\s*=\\s*(\\d+)`));
  assert.ok(m, `${name} not found in the page`);
  return Number(m[1]);
}

function serverNumber(name) {
  const m = readFileSync(SERVER, "utf8").match(new RegExp(`^${name}\\s*=\\s*(\\d+)`, "m"));
  assert.ok(m, `${name} not found in the server`);
  return Number(m[1]);
}

test("the page and the server use the same level range", () => {
  assert.equal(pageNumber("MIN_LEVEL"), serverNumber("MIN_LEVEL"));
  assert.equal(pageNumber("MAX_LEVEL"), serverNumber("MAX_LEVEL"));
});

test("the page and the server use the same level names", () => {
  const page = readCode(PAGE).match(/LEVEL_NAMES[^=]*=\s*\{([^}]*)\}/);
  const server = readFileSync(SERVER, "utf8").match(/LEVEL_NAMES\s*=\s*\{([^}]*)\}/);
  assert.ok(page && server, "LEVEL_NAMES not found on one side");
  const pairs = (s) => [...s.matchAll(/(\d+)\s*:\s*"([^"]+)"/g)].map((m) => `${m[1]}=${m[2]}`);
  assert.deepEqual(pairs(page[1]), pairs(server[1]));
});

test("every route the page calls is served by the router", () => {
  const router = readFileSync(ROUTER, "utf8");
  const prefix = router.match(/prefix="([^"]+)"/)[1];
  assert.equal(prefix, "/skills-management");
  const served = [...router.matchAll(/@router\.(get|post|put|delete)\("([^"]*)"/g)].map(
    (m) => `${m[1].toUpperCase()} ${prefix}${m[2]}`,
  );
  const wanted = [
    "GET /skills-management/employees/{employee_id}/skills",
    "POST /skills-management/employees/{employee_id}/skills",
    "DELETE /skills-management/employees/{employee_id}/skills",
    "GET /skills-management/roles",
    "GET /skills-management/roles/requirements",
    "PUT /skills-management/roles/requirements",
  ];
  for (const w of wanted) assert.ok(served.includes(w), `router does not serve ${w}`);
  const page = readCode(PAGE);
  assert.ok(page.includes("/skills-management/employees/${employeeId}/skills"));
  assert.ok(page.includes('method: "DELETE"'));
  assert.ok(page.includes('method: "PUT"'));
  assert.ok(page.includes("/skills-management/roles/requirements"));
});

test("the page is reachable from the navigation", () => {
  assert.ok(readCode(NAV).includes('href: "/app/employee-skills"'));
});
