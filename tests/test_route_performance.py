import json
import threading
import unittest
from urllib.parse import parse_qs, urlsplit

import route_tool as tool
from test_route_tool import build, FSDS, Server


class RoutePerformanceTests(unittest.TestCase):
    def test_cache_is_bounded_expiring_and_returns_copies(self):
        clock = [0]
        cache = tool.SystemCache(capacity=2, ttl=10, clock=lambda: clock[0])
        cache.put('A', dict(name='A', id64='1'))
        cache.put('B', dict(name='B', id64='2'))
        cached = cache.get(' a ')
        cached['id64'] = 'wrong'
        self.assertEqual(cache.get('A')['id64'], '1')
        cache.put('C', dict(name='C', id64='3'))
        self.assertIsNone(cache.get('B'))
        clock[0] = 10
        self.assertIsNone(cache.get('A'))

    def test_exact_resolutions_are_cached_but_errors_are_not(self):
        cache, calls = tool.SystemCache(), []
        def http(url):
            name = parse_qs(urlsplit(url).query)['q'][0]
            calls.append(name)
            return dict(min_max=[dict(name='A', id64=1)])
        self.assertEqual(tool.resolve('A', http, cache)['id64'], '1')
        self.assertEqual(tool.resolve('a', http, cache)['id64'], '1')
        self.assertEqual(calls, ['A'])
        for _ in range(2):
            with self.assertRaises(ValueError):
                tool.resolve('Wrong', http, cache)
        self.assertEqual(calls, ['A', 'Wrong', 'Wrong'])

    def test_two_overlapping_resolutions_preserve_order_and_deduplicate(self):
        lock, barrier = threading.Lock(), threading.Barrier(2)
        active, maximum, calls = 0, 0, []
        def http(url):
            nonlocal active, maximum
            name = parse_qs(urlsplit(url).query)['q'][0]
            with lock:
                calls.append(name)
                active += 1
                maximum = max(maximum, active)
            try:
                barrier.wait(timeout=3)
                return dict(min_max=[dict(name=name.upper(), id64=ord(name.upper()))])
            finally:
                with lock:
                    active -= 1
        resolved = tool.resolve_points(['A', 'B', 'C', 'D', 'a'], http=http)
        self.assertEqual([p['name'] for p in resolved], ['A', 'B', 'C', 'D', 'A'])
        self.assertEqual(len(calls), 4)
        self.assertEqual(maximum, 2)

    def test_cancel_during_resolution_never_submits_route_or_more_points(self):
        stop, release, started = threading.Event(), threading.Event(), threading.Event()
        calls, results, route_posts = [], [], []
        lock = threading.Lock()
        def http(url, payload=None):
            if payload is not None:
                route_posts.append(payload)
            self.assertIsNone(payload)
            name = parse_qs(urlsplit(url).query)['q'][0]
            with lock:
                calls.append(name)
                if len(calls) == 2:
                    started.set()
            release.wait(3)
            return dict(min_max=[dict(name=name, id64=ord(name))])
        thread = threading.Thread(target=lambda: results.append(tool.plan(
            json.dumps(build()), ['A', 'B', 'C'], tool.Options(), stop, http=http, fsds=FSDS)))
        thread.start()
        try:
            self.assertTrue(started.wait(3))
            stop.set()
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertFalse(results[0]['complete'])
            self.assertEqual(results[0]['rows'], [])
            self.assertEqual(len(calls), 2)
            self.assertEqual(route_posts, [])
        finally:
            release.set()
            thread.join(3)

    def test_failure_to_resolve_any_endpoint_prevents_all_route_jobs(self):
        server = Server()
        def http(url, payload=None):
            if 'q=C' in url:
                return dict(min_max=[])
            return server(url, payload)
        info = tool.plan(json.dumps(build()), ['A', 'B', 'C'], tool.Options(), http=http, fsds=FSDS)
        self.assertFalse(info['complete'])
        self.assertEqual(server.requests, [])

    def test_repeated_plans_reuse_only_resolution_not_route_jobs_and_report_timings(self):
        server, cache, lookups, events = Server(), tool.SystemCache(), [], []
        def http(url, payload=None):
            if '/field_values/' in url:
                lookups.append(url)
            return server(url, payload)
        for _ in range(2):
            info = tool.plan(json.dumps(build()), ['A', 'B'], tool.Options(), http=http,
                             fsds=FSDS, resolver_cache=cache,
                             progress=lambda text, detail: events.append(detail))
            self.assertTrue(info['complete'], info['reason'])
        self.assertEqual(len(lookups), 2)
        self.assertEqual(len(server.requests), 2)
        self.assertTrue(any(e['stage'] == '星系解析' for e in events))
        self.assertTrue(all(info['timings'][key] >= 0 for key in
                            ('ship_seconds', 'resolve_seconds', 'route_seconds', 'total_seconds')))

    def test_running_job_does_not_keep_ten_second_queue_backoff(self):
        states = iter(['queued'] * 5 + ['running'] * 2 + ['completed'])
        delays, submissions = [], []
        def http(url, payload=None):
            if payload is not None:
                submissions.append(payload)
                return dict(job='job1', status='queued')
            state = next(states)
            return dict(state=state, result={})
        tool.plot_job({}, http=http, wait=delays.append)
        self.assertEqual(delays[:5], [2, 3, 4.5, 6.75, 10])
        self.assertEqual(delays[5:], [4, 4])
        self.assertEqual(len(submissions), 1)
