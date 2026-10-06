import { test, expect } from "@playwright/test";

// Drives the public /chat client through the generic demo survey against a
// running stack (voice-agent on the configured WS URL). Uses the real
// local LLM, so turns can take several seconds — timeouts are generous.
test("demo survey advances through the first turn", async ({ page }) => {
  await page.goto("/chat");

  // The input enables once the WebSocket connects.
  const input = page.getByPlaceholder(/type your message/i);
  await expect(input).toBeEnabled({ timeout: 30_000 });

  // The runner speaks the welcome interstitial + the first question on setup.
  await expect(page.getByText(/what's your first name/i)).toBeVisible({
    timeout: 90_000,
  });

  // Answer the first (free-text) question.
  await input.fill("Alex");
  await page.getByRole("button", { name: "Send" }).click();

  // The LLM interprets the name, records it, and the survey advances to the
  // next (single-choice) question.
  await expect(page.getByText(/used a voice assistant before/i)).toBeVisible({
    timeout: 120_000,
  });
});
