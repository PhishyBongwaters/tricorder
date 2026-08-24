/** Package-owned tricorder-inject invariants. @module @deepseek-ai/dsh-tricorder-inject/invariant */

import type { InvariantInstaller } from '@deepseek-ai/dsh-invariants'

export const name = 'tricorder-inject-invariant'
export const inject = ['invariants'] as const

const PACKAGE_NAME = '@deepseek-ai/dsh-tricorder-inject'

export const install: InvariantInstaller = (ctx, fail) => {
  if (!ctx.get('sessions')) {
    fail('tricorder-inject requires @deepseek-ai/dsh-session (sessions service)')
  }
  if (!ctx.get('systemPrompt')) {
    fail('tricorder-inject requires @deepseek-ai/dsh-system-prompt (systemPrompt service)')
  }
}