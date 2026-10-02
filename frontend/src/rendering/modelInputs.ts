import type { GridInputs, LandcoverClass, Resolution } from '../types/simulation'

/**
 * A grid's static model inputs as the client keeps them: terrain Z and land cover, row-major like a frame's depth
 * grid, plus each cell's Manning's n looked up from the class table - the same table the backend builds N from,
 * so it is exactly the roughness the engine runs on. The arrays sit in private fields for the same reason as
 * DepthGrid's (React's dev-mode prop diffing would enumerate a shallowly reachable typed array).
 */
export class ModelInputs {
  readonly resolution: Resolution
  readonly rows: number
  readonly cols: number
  /** Cell size, m. */
  readonly dx: number
  readonly classes: readonly LandcoverClass[]
  readonly minElevation: number
  readonly maxElevation: number
  readonly #elevation: Float32Array
  readonly #landcover: Uint8Array
  readonly #roughness: Float32Array
  readonly #classById: ReadonlyMap<number, LandcoverClass>

  constructor(inputs: GridInputs) {
    const [rows, cols] = inputs.grid_shape
    this.resolution = inputs.resolution
    this.rows = rows
    this.cols = cols
    this.dx = inputs.dx
    this.classes = inputs.classes
    this.#elevation = Float32Array.from(inputs.elevation)
    this.#landcover = Uint8Array.from(inputs.landcover)
    this.#classById = new Map(inputs.classes.map((c) => [c.id, c]))
    this.#roughness = new Float32Array(rows * cols)
    let min = Infinity
    let max = -Infinity
    for (let cell = 0; cell < rows * cols; cell++) {
      this.#roughness[cell] = this.#classById.get(this.#landcover[cell])?.manning_n ?? NaN
      min = Math.min(min, this.#elevation[cell])
      max = Math.max(max, this.#elevation[cell])
    }
    this.minElevation = min
    this.maxElevation = max
  }

  get elevation(): Float32Array {
    return this.#elevation
  }

  get landcover(): Uint8Array {
    return this.#landcover
  }

  /** Manning's n per cell. */
  get roughness(): Float32Array {
    return this.#roughness
  }

  classOf(cell: number): LandcoverClass | null {
    return this.#classById.get(this.#landcover[cell]) ?? null
  }
}
