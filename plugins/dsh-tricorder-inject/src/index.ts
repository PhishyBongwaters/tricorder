/**
 * Tricorder Turn-0 Injection for DeepSeek Harness (dsh)
 *
 * Cordis plugin that injects the unified tricorder "probe digest" into new
 * sessions at turn 0 (before the first turn/start event).
 *
 * Turn 0 is a NAVIGATION item, not a deep dive: it emits the same cheap
 * language-tally + navigation-hint digest that the Hermes plugin injects, via
 * the shared `tricorder --probe-digest` CLI flag. It never builds the full repo
 * map on turn 0 — on a kernel-scale tree that would block/timeout. Maps are
 * built on demand via /tricorder scan or the MCP tools.
 *
 * @module @deepseek-ai/dsh-tricorder-inject
 */

import { Context, Service } from '@deepseek-ai/cordis'
import { Session } from '@deepseek-ai/dsh-session'
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import { promisify } from 'node:util'
import { execFile } from 'node:child_process'
import { resolve } from 'node:path'

const execFileAsync = promisify(execFile)

export interface TricorderInjectConfig {
  /** Explicit path to the tricorder CLI (auto-detected if not provided) */
  tricorderExe?: string
  /** Enable verbose logging */
  verbose?: boolean
}

/**
 * Turn-0 probe-digest injector.
 * Listens for session/created and injects the digest before turn 1.
 */
export class TricorderInjector extends Service {
  static inject = ['sessions']

  private readonly config: Required<TricorderInjectConfig>
  private readonly exe: string

  constructor(ctx: Context, config: TricorderInjectConfig) {
    super(ctx, 'tricorderInjector')

    this.config = {
      tricorderExe: config.tricorderExe ?? '',
      verbose: config.verbose ?? false,
    }
    this.exe = this.resolveExe(this.config.tricorderExe)

    // Seed existing sessions
    for (const session of ctx.sessions.list()) {
      this.injectIntoSession(session)
    }

    // Hook new sessions (global = all scopes)
    ctx.on('session/created', (session: Session) => this.injectIntoSession(session), { global: true })
  }

  private resolveExe(exe: string | undefined): string {
    if (exe) return exe
    // Auto-detect common locations
    const candidates = [
      resolve('D:/Projects/tricorder/.venv/Scripts/tricorder.exe'),
      resolve(process.env.APPDATA || '', 'Python/Python314/Scripts/tricorder.exe'),
      'tricorder', // on PATH
    ]
    return candidates.find(c => {
      try {
        return require('node:fs').existsSync(c)
      } catch {
        return false
      }
    }) || 'tricorder'
  }

  /** Emit the shared probe digest (pure CLI passthrough — the digest text is
   * owned by the tricorder CLI so Hermes and DSH stay byte-identical). */
  async probeDigest(root: string): Promise<string> {
    const { stdout, stderr } = await execFileAsync(this.exe, [
      '--root', root,
      '--probe-digest',
    ], {
      timeout: 30_000,
      maxBuffer: 256 * 1024,
    })
    void stderr
    return stdout.trim()
  }

  private async injectIntoSession(session: Session): Promise<void> {
    // Guard: only inject at turn 0 (no turn/start event yet)
    const hasTurnStart = session.events.some(e => e.type === 'turn/start')
    if (hasTurnStart) {
      if (this.config.verbose) this.ctx.logger.debug('[tricorder-inject] session not at turn 0, skipping')
      return
    }

    const cwd = session.header.cwd
    if (!cwd) {
      if (this.config.verbose) this.ctx.logger.debug('[tricorder-inject] session has no cwd, skipping')
      return
    }

    try {
      // Turn 0 = cheap navigation probe only. Never a full map build.
      const digestText = await this.probeDigest(cwd)
      if (!digestText) {
        // Empty/tiny/non-code repo (or CLI unavailable) — nothing to inject.
        if (this.config.verbose) this.ctx.logger.debug('[tricorder-inject] empty digest, skipping')
        return
      }
      const message = `[tricorder] ${cwd} — ${digestText}`
      session.append('user/message', createUserMessage({
        content: [{ type: 'text', text: message }],
        source: { kind: 'plugin', plugin: 'tricorder' },
      }), { surfaceOp: 'append' })

      if (this.config.verbose) {
        this.ctx.logger.info(
          `[tricorder-inject] session ${session.id}: injected turn-0 probe digest (${digestText.length} chars)`
        )
      }
    } catch (error) {
      if (this.config.verbose) {
        this.ctx.logger.warn(`[tricorder-inject] session ${session.id}: ${error}`)
      }
      // Silent fail - injection is best-effort
    }
  }
}

/** Cordis plugin entry point */
export const apply = (ctx: Context, config: TricorderInjectConfig = {}): TricorderInjector => {
  return new TricorderInjector(ctx, config)
}

export default TricorderInjector