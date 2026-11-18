const OWNER = 'rodolfochoi911-lgtm';
const MAX_LATENESS_MS = 5 * 60 * 1000;

export function targetFor(cron) {
  switch (cron) {
    case '0 21 * * *':
      return { repo: 'mvno-market-monitor', workflow: 'market_monitor.yml', inputs: { test_mode: false } };
    case '7 21 * * *':
    case '12 6 * * *':
      return { repo: 'competitor-monitor', workflow: 'run_monitor.yml', inputs: {} };
    case '3-59/10 * * * *':
      return { repo: 'mvno-market-monitor', workflow: 'dc_event_alerts.yml', inputs: { dry_run: false } };
    default:
      throw new Error('Unknown cron; no workflow dispatched');
  }
}

export async function dispatchScheduled(event, env, fetcher = fetch, now = Date.now()) {
  if (env.ENABLED !== 'true') {
    console.log('Scheduler disabled; existing GitHub schedules remain in use');
    return { disabled: true };
  }
  const target = targetFor(event.cron);
  const scheduled = Number(event.scheduledTime);
  if (!Number.isFinite(scheduled) || scheduled <= 0 || scheduled > now || now - scheduled > MAX_LATENESS_MS) {
    throw new Error('Invalid or stale schedule; no late catch-up dispatch');
  }
  if (!env.GITHUB_TOKEN) throw new Error('GITHUB_TOKEN secret is missing');
  const scheduledAt = new Date(scheduled).toISOString();
  const url = `https://api.github.com/repos/${OWNER}/${target.repo}/actions/workflows/${target.workflow}/dispatches`;
  let response;
  try {
    response = await fetcher(url, {
      method: 'POST',
      headers: {
        Accept: 'application/vnd.github+json',
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'mvno-cloudflare-scheduler',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        ref: 'main',
        inputs: { ...target.inputs, scheduled_at: scheduledAt, schedule_source: 'cloudflare' },
      }),
      // Workers supports manual/follow only. Reject 3xx below without forwarding credentials.
      redirect: 'manual',
      signal: AbortSignal.timeout(15000),
    });
  } catch {
    // A lost response may already have created a run: do not retry POST blindly.
    throw new Error(`Dispatch outcome unknown for ${target.repo}/${target.workflow}; inspect Actions before retrying`);
  }
  if (![200, 204].includes(response.status)) {
    // Never log response bodies: they may contain access details.
    throw new Error(`GitHub dispatch rejected: HTTP ${response.status} (${target.repo}/${target.workflow})`);
  }
  const result = { repo: target.repo, workflow: target.workflow, scheduled_at: scheduledAt, accepted: true };
  console.log(JSON.stringify(result));
  return result;
}

export default {
  async scheduled(event, env) {
    await dispatchScheduled(event, env);
  },
  fetch() {
    // There is no public HTTP endpoint capable of triggering a workflow.
    return new Response('Not found', { status: 404 });
  },
};
