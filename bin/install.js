#!/usr/bin/env node
'use strict';

const { execSync } = require('child_process');
const args = process.argv.slice(2);

const REPO = 'high-oss/high_skills';
const SKILL = 'high';

if (args.includes('--help') || args.includes('-h')) {
  console.log(`
@high-oss/high-skill — HIGH agent skill installer

Usage:
  npx @high-oss/high-skill              Install for current agent
  npx @high-oss/high-skill -- -a codex  Install for Codex
  npx @high-oss/high-skill -- -a claude Install for Claude Code
  npx @high-oss/high-skill --help       Show this help

Internally runs:
  npx skills add ${REPO} --skill ${SKILL} [extra args]
`);
  process.exit(0);
}

const extra = args.length ? ' ' + args.join(' ') : '';
const cmd = `npx skills add ${REPO} --skill ${SKILL}${extra}`;

console.log(`\nInstalling HIGH skill...\n  ${cmd}\n`);

try {
  execSync(cmd, { stdio: 'inherit' });
} catch (err) {
  process.exit(err.status || 1);
}
