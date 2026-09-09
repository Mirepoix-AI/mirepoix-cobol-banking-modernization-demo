// Invoke the captured, hash-identified real @mirepoix/validate public entry point.
const platform = process.argv[2];
if (!platform) throw new Error("captured platform path required");
const { validate } = await import(`${platform}/packages/validate/src/index.ts`);
const request = JSON.parse(await Bun.stdin.text());
const startedAt = Date.now() / 1000;
try {
  const rawVerdict = validate(request);
  process.stdout.write(JSON.stringify({ schemaVersion: 1, startedAt, endedAt: Date.now() / 1000, rawVerdict }) + "\n");
} catch (error) {
  process.stdout.write(JSON.stringify({ schemaVersion: 1, startedAt, endedAt: Date.now() / 1000, rawVerdict: null,
    error: { name: (error as Error).name, message: (error as Error).message } }) + "\n");
  process.exitCode = 1;
}
