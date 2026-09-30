import test from "node:test";
import assert from "node:assert/strict";
import { appName } from "../src/app.js";

test("frontend scaffold is importable", () => {
  assert.equal(appName, "invoice-filler");
});

