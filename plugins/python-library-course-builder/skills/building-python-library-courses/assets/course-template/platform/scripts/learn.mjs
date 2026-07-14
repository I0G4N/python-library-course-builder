import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const platformRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(platformRoot, "..");
const runnerEnvironment = {
  ...process.env,
  COURSEKIT_ROOT: platformRoot,
  COURSEKIT_COURSE_DIR: resolve(platformRoot, "course"),
  COURSEKIT_WORKSPACE_DIR:
    process.env.COURSEKIT_WORKSPACE_DIR ?? resolve(repositoryRoot, "labs"),
  UV_CACHE_DIR: resolve(platformRoot, ".uv-cache"),
};

const supportsProcessGroups = process.platform !== "win32";
const parsedShutdownGrace = Number.parseInt(
  process.env.COURSEKIT_SHUTDOWN_GRACE_MS ?? "2000",
  10,
);
const shutdownGraceMilliseconds =
  Number.isFinite(parsedShutdownGrace) && parsedShutdownGrace >= 0
    ? parsedShutdownGrace
    : 2_000;
const children = [];
const childState = new WeakMap();
let shuttingDown = false;
let shutdownCode = 0;
let forceExitTimer;
let shutdownPollTimer;

function start(command, args, label) {
  const child = spawn(command, args, {
    cwd: platformRoot,
    detached: supportsProcessGroups,
    env: runnerEnvironment,
    stdio: "inherit",
  });
  childState.set(child, { spawnFailed: false });
  child.on("error", (error) => {
    childState.get(child).spawnFailed = true;
    console.error(`[${label}] failed to start: ${error.message}`);
    shutdown(1);
  });
  children.push(child);
  return child;
}

function hasExited(child) {
  return (
    childState.get(child)?.spawnFailed ||
    child.exitCode !== null ||
    child.signalCode !== null
  );
}

function isProcessGroupAlive(child) {
  if (!supportsProcessGroups || child.pid === undefined) return false;
  try {
    process.kill(-child.pid, 0);
    return true;
  } catch (error) {
    if (error.code === "ESRCH") return false;
    if (error.code === "EPERM") return true;
    throw error;
  }
}

function hasStopped(child) {
  return hasExited(child) && !isProcessGroupAlive(child);
}

function signalChildTree(child, signal) {
  if (supportsProcessGroups && child.pid !== undefined) {
    try {
      process.kill(-child.pid, signal);
      return;
    } catch (error) {
      if (error.code === "ESRCH") return;
      console.error(
        `[launcher] could not signal process group ${child.pid}: ${error.message}`,
      );
    }
  }

  if (!hasExited(child)) child.kill(signal);
}

function finishShutdownIfReady() {
  if (shuttingDown && children.every(hasStopped)) {
    if (forceExitTimer) clearTimeout(forceExitTimer);
    if (shutdownPollTimer) clearTimeout(shutdownPollTimer);
    process.exit(shutdownCode);
  }
}

function pollForShutdown() {
  if (!shuttingDown || shutdownPollTimer) return;
  shutdownPollTimer = setTimeout(() => {
    shutdownPollTimer = undefined;
    finishShutdownIfReady();
    if (shuttingDown) pollForShutdown();
  }, 25);
}

function forceShutdown() {
  forceExitTimer = undefined;
  for (const child of children) {
    if (!hasStopped(child)) signalChildTree(child, "SIGKILL");
  }
  finishShutdownIfReady();
  pollForShutdown();
}

function shutdown(code = 0) {
  if (code !== 0) shutdownCode = code;
  if (shuttingDown) {
    finishShutdownIfReady();
    return;
  }
  shuttingDown = true;
  for (const child of children) {
    if (!hasStopped(child)) signalChildTree(child, "SIGTERM");
  }
  finishShutdownIfReady();
  pollForShutdown();
  forceExitTimer = setTimeout(forceShutdown, shutdownGraceMilliseconds);
}

console.log("\nCourseKit is starting the course UI and local CPython runner…\n");
const runner = start(
  "uv",
  ["run", "uvicorn", "runner.app:app", "--host", "127.0.0.1", "--port", "8765"],
  "runner",
);
const site = start("npm", ["run", "dev"], "site");

for (const child of [runner, site]) {
  child.on("exit", (code, signal) => {
    if (shuttingDown) {
      finishShutdownIfReady();
      return;
    }
    console.error(`\nA CourseKit process stopped (${code ?? signal}).`);
    shutdown(code ?? 1);
  });
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));
