export type ScoreSegment = 'green' | 'yellow' | 'red'

export interface ScoreRange {
  min?: number
  max?: number
}

/**
 * Convert score segment to API parameters
 */
export function scoreSegmentToRange(segment: ScoreSegment | null): ScoreRange {
  switch (segment) {
    case 'green':
      return { min: 80 }
    case 'yellow':
      return { min: 50, max: 79 }
    case 'red':
      return { max: 49 }
    default:
      return {}
  }
}

/**
 * Convert API range back to segment for UI
 */
export function rangeToScoreSegment(min?: number, max?: number): ScoreSegment | null {
  if (min === 80 && !max) return 'green'
  if (min === 50 && max === 79) return 'yellow'
  if (!min && max === 49) return 'red'
  return null
}

/**
 * Get score segment display name
 */
export function getScoreSegmentLabel(segment: ScoreSegment): string {
  switch (segment) {
    case 'green':
      return '🟢 80+'
    case 'yellow':
      return '🟡 50-79'
    case 'red':
      return '🔴 0-49'
  }
}