import { describe, expect, it } from 'vitest';

import { BoundedWindowCache } from '../src/replay/windowCache';

describe('bounded replay window cache', () => {
  it('evicts the least recently used window and remains bounded', () => {
    const cache = new BoundedWindowCache<number>(2);
    cache.set('first', 1);
    cache.set('second', 2);
    expect(cache.get('first')).toBe(1);
    cache.set('third', 3);
    expect(cache.size).toBe(2);
    expect(cache.peek('second')).toBeUndefined();
    expect(cache.peek('first')).toBe(1);
    expect(cache.peek('third')).toBe(3);
  });

  it('rejects an unbounded or empty cache configuration', () => {
    expect(() => new BoundedWindowCache(0)).toThrow(/positive integer/);
  });
});
