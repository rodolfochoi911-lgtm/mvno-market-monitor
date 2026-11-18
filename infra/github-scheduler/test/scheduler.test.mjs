import test from 'node:test';
import assert from 'node:assert/strict';
import worker, { dispatchScheduled, targetFor } from '../src/index.mjs';

const time = Date.parse('2026-11-17T21:07:00Z');
const env = { ENABLED: 'true', GITHUB_TOKEN: 'test-secret' };
const event = { cron: '7 21 * * *', scheduledTime: time };

test('daily schedules map to intended KST times and repositories', () => {
  assert.equal(targetFor('0 21 * * *').workflow, 'market_monitor.yml');
  for (const cron of ['7 21 * * *', '12 6 * * *']) {
    assert.equal(targetFor(cron).repo, 'competitor-monitor');
  }
  assert.equal(targetFor('3-59/10 * * * *').inputs.dry_run, false);
  assert.throws(() => targetFor('* * * * *'));
});

test('disabled deployment never calls GitHub', async () => {
  const result = await dispatchScheduled(event, {}, () => { throw new Error('must not call'); }, time);
  assert.deepEqual(result, { disabled: true });
});

test('dispatch includes original schedule and uses only main', async () => {
  let call;
  const result = await dispatchScheduled(event, env, async (...args) => {
    call = args;
    return new Response(null, { status: 204 });
  }, time + 2000);
  assert.match(call[0], /competitor-monitor\/actions\/workflows\/run_monitor.yml\/dispatches$/);
  assert.equal(call[1].method, 'POST');
  assert.equal(call[1].redirect, 'error');
  assert.deepEqual(JSON.parse(call[1].body), {
    ref: 'main', inputs: { scheduled_at: '2026-11-17T21:07:00.000Z', schedule_source: 'cloudflare' },
  });
  assert.equal(result.accepted, true);
});

test('DC dispatch explicitly enables the existing notification job', async () => {
  await dispatchScheduled({ ...event, cron: '3-59/10 * * * *' }, env, async (url, init) => {
    assert.equal(JSON.parse(init.body).inputs.dry_run, false);
    assert.match(url, /dc_event_alerts.yml/);
    return new Response(null, { status: 204 });
  }, time);
});

test('GitHub response with run details is also accepted', async () => {
  const result = await dispatchScheduled(event, env,
    async () => new Response(JSON.stringify({ workflow_run_id: 123 }), { status: 200 }), time);
  assert.equal(result.accepted, true);
});

test('stale, future, and malformed events are rejected before network access', async () => {
  for (const scheduledTime of [time - 300001, time + 1, NaN, 0]) {
    await assert.rejects(dispatchScheduled({ ...event, scheduledTime }, env,
      () => assert.fail('must not call'), time), /Invalid or stale/);
  }
});

test('missing token fails before dispatch', async () => {
  await assert.rejects(dispatchScheduled(event, { ENABLED: 'true' },
    () => assert.fail('must not call'), time), /secret is missing/);
});

test('GitHub failures expose status without response contents or secrets', async () => {
  for (const status of [401, 403, 422, 429, 500]) {
    await assert.rejects(dispatchScheduled(event, env,
      async () => new Response('sensitive response', { status }), time), error => {
      assert.match(error.message, new RegExp(`HTTP ${status}`));
      assert.doesNotMatch(error.message, /sensitive|test-secret/);
      return true;
    });
  }
});

test('ambiguous POST failures are never retried and raw exceptions are redacted', async () => {
  let count = 0;
  await assert.rejects(dispatchScheduled(event, env, async () => {
    count++;
    throw new Error('test-secret');
  }, time), error => {
    assert.match(error.message, /outcome unknown/);
    assert.doesNotMatch(error.message, /test-secret/);
    return true;
  });
  assert.equal(count, 1);
});

test('HTTP requests cannot dispatch workflows', async () => {
  assert.equal(worker.fetch().status, 404);
});
