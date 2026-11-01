import { describe, expect, it } from 'vitest'
import { ratio, verdict, type Side } from './compare'

function side(errors: number, low: number, high: number): Side {
  return { errors, rate: errors / 1000, low, high }
}

describe('the verdict', () => {
  it('is within while the intervals touch, whatever the point estimates say', () => {
    expect(verdict(side(30, 0.021, 0.042), side(20, 0.013, 0.031))).toBe('within')
    expect(verdict(side(30, 0.021, 0.042), side(30, 0.021, 0.042))).toBe('within')
  })

  it('is lower only when the judged interval sits wholly below the reference', () => {
    expect(verdict(side(300, 0.272, 0.329), side(100, 0.083, 0.120))).toBe('lower')
  })

  it('is higher only when the judged interval sits wholly above the reference', () => {
    expect(verdict(side(100, 0.083, 0.120), side(300, 0.272, 0.329))).toBe('higher')
  })

  it('treats intervals that meet at an endpoint as touching', () => {
    expect(verdict(side(10, 0.005, 0.02), side(30, 0.02, 0.04))).toBe('within')
  })
})

describe('the ratio', () => {
  it('is the judged rate over the reference rate', () => {
    expect(ratio(side(30, 0, 1), side(15, 0, 1))).toBeCloseTo(0.5)
  })

  it('is undefined when the reference saw no error', () => {
    expect(ratio(side(0, 0, 0.004), side(3, 0.001, 0.009))).toBeNull()
  })
})
