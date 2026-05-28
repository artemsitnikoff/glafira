import { useEffect, useState } from 'react'

/**
 * Debounce hook for delaying value changes
 * @param value - The value to debounce
 * @param delay - Delay in milliseconds (default: 200)
 */
export function useDebounce<T>(value: T, delay: number = 200): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value)
    }, delay)

    return () => {
      clearTimeout(timer)
    }
  }, [value, delay])

  return debouncedValue
}