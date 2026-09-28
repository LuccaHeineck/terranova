import type { GridShape } from '../types/simulation'
import type { CompactFrame } from './depthGrid'

/**
 * Memory budget for one run's buffered frames. At 4 bytes per cell that is 238 frames of the 30m grid
 * (35,136 cells, 140.5 KB each) or, capped by MAX_CAPACITY, 2,048 frames of the 90m grid (3,904 cells, 15.6 KB
 * each) - enough for a whole 90m run to the May 2024 peak (~270 frames at the default interval) unthinned.
 */
export const BUFFER_BUDGET_BYTES = 32 * 1024 * 1024
const MIN_CAPACITY = 64
const MAX_CAPACITY = 2048

export interface BufferedFrame {
  /** Position in the order frames were received (0-based); decides which frames survive thinning. */
  index: number
  frame: CompactFrame
}

/**
 * A run's received frames, bounded by decimation. Every `stride`-th received frame is kept, plus always the
 * newest one (the tail, which is what "live" shows). When the kept frames would exceed `capacity`, every other
 * one is dropped and `stride` doubles. So however long the run gets, the buffer holds between capacity/2 and
 * capacity frames spread evenly over the whole run, always including the first and the latest.
 */
export interface FrameBuffer {
  /** Identifies the run the buffer belongs to; unchanged by appends. */
  id: number
  shape: GridShape
  capacity: number
  stride: number
  received: number
  /** Ascending by index. All on-stride except possibly the last, the newest frame. */
  entries: BufferedFrame[]
}

let nextBufferId = 1

export function bytesPerFrame({ rows, cols }: GridShape): number {
  return rows * cols * Float32Array.BYTES_PER_ELEMENT
}

export function capacityFor(shape: GridShape): number {
  const fits = Math.floor(BUFFER_BUDGET_BYTES / bytesPerFrame(shape))
  return Math.min(MAX_CAPACITY, Math.max(MIN_CAPACITY, fits))
}

export function createFrameBuffer(shape: GridShape): FrameBuffer {
  return { id: nextBufferId++, shape, capacity: capacityFor(shape), stride: 1, received: 0, entries: [] }
}

/** Returns a new buffer with `frame` appended as the newest, thinning older frames if it is now over capacity. */
export function appendFrame(buffer: FrameBuffer, frame: CompactFrame): FrameBuffer {
  const index = buffer.received
  let { stride } = buffer
  // The previous tail was kept only for being the newest; it goes if it is off-stride.
  const tail = buffer.entries.at(-1)
  let entries = tail && tail.index % stride !== 0 ? buffer.entries.slice(0, -1) : buffer.entries.slice()
  entries.push({ index, frame })
  if (entries.length > buffer.capacity) {
    stride *= 2
    const newest = entries.length - 1
    entries = entries.filter((entry, i) => entry.index % stride === 0 || i === newest)
  }
  return { ...buffer, stride, received: index + 1, entries }
}

/** Index of the last buffered frame at or before `step` (0 if none is). Frames are ascending by step. */
export function indexAtOrBefore(buffer: FrameBuffer, step: number): number {
  const { entries } = buffer
  let lo = 0
  let hi = entries.length - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (entries[mid].frame.step <= step) lo = mid
    else hi = mid - 1
  }
  return lo
}

export function bufferBytes(buffer: FrameBuffer): number {
  return buffer.entries.length * bytesPerFrame(buffer.shape)
}
