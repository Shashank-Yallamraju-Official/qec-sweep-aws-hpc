import { describe, expect, it } from 'vitest'
import type { Run } from './catalogue'
import { assignColours, defaults, fromUrl, toSearch } from './selection'

function run(name: string): Run {
  return {
    key: `s3://bucket/sweeps/${name}`,
    kind: 'sweeps',
    run: name,
    submitted: new Date(0),
    finished: null,
    queue: 'sweep',
    commit: null,
    image: null,
    imageDigest: null,
    clusterConfigSha256: null,
    instanceType: null,
    nodes: null,
    nodesUsed: null,
    seed: null,
    parents: [],
    jobs: {},
    parameters: {},
    cells: 40,
  }
}

const runs = [run('newest'), run('middle'), run('oldest')]

describe('the address', () => {
  it('names runs by their run name and resolves them to keys', () => {
    expect(fromUrl(runs, '?a=oldest&b=newest')).toEqual({
      a: 's3://bucket/sweeps/oldest',
      b: 's3://bucket/sweeps/newest',
    })
    expect(toSearch(runs, { a: 's3://bucket/sweeps/oldest', b: 's3://bucket/sweeps/newest' })).toBe(
      '?a=oldest&b=newest',
    )
  })

  it('drops a name the catalogue does not have', () => {
    expect(fromUrl(runs, '?a=gone&b=newest')).toEqual({ a: null, b: 's3://bucket/sweeps/newest' })
    expect(toSearch(runs, { a: null, b: null })).toBe('')
  })
})

describe('the defaults', () => {
  it('judge the newest run against the one before it', () => {
    expect(defaults(runs)).toEqual({ a: 's3://bucket/sweeps/middle', b: 's3://bucket/sweeps/newest' })
  })

  it('leave a slot empty when there is only one run', () => {
    expect(defaults([run('only')])).toEqual({ a: null, b: 's3://bucket/sweeps/only' })
  })
})

describe('colours', () => {
  it('give the first two runs the two hues in order', () => {
    const colours = assignColours(new Map(), { a: 'x', b: 'y' })
    expect([...colours]).toEqual([
      ['x', 1],
      ['y', 2],
    ])
  })

  it('stay with a run when the slots are swapped', () => {
    const first = assignColours(new Map(), { a: 'x', b: 'y' })
    const swapped = assignColours(first, { a: 'y', b: 'x' })
    expect(swapped.get('x')).toBe(1)
    expect(swapped.get('y')).toBe(2)
  })

  it('give a newly chosen run the hue the other run is not wearing', () => {
    const first = assignColours(new Map(), { a: 'x', b: 'y' })
    const replaced = assignColours(first, { a: 'x', b: 'z' })
    expect(replaced.get('z')).toBe(2)
    expect(replaced.has('y')).toBe(false)
    const other = assignColours(first, { a: 'w', b: 'y' })
    expect(other.get('w')).toBe(1)
  })
})
