<template>
  <div class="usage-chart">
    <div class="usage-chart-header">
      <h6 class="usage-chart-title">{{ title }}</h6>
      <div class="usage-chart-legend">
        <span class="usage-chart-legend-item"><i class="usage-chart-swatch usage-chart-swatch-allowed"></i>Consentiti</span>
        <span class="usage-chart-legend-item"><i class="usage-chart-swatch usage-chart-swatch-denied"></i>Negati</span>
      </div>
    </div>

    <div v-if="!hasData" class="text-muted small py-4 text-center">Nessun dato disponibile.</div>
    <svg v-else :viewBox="`0 0 ${width} ${height}`" class="usage-chart-svg" preserveAspectRatio="none">
      <line
        v-for="(tick, i) in yTicks"
        :key="`grid-${i}`"
        :x1="padding.left"
        :x2="width - padding.right"
        :y1="yScale(tick)"
        :y2="yScale(tick)"
        class="usage-chart-gridline"
      />
      <text
        v-for="(tick, i) in yTicks"
        :key="`ytick-${i}`"
        :x="padding.left - 8"
        :y="yScale(tick) + 3"
        class="usage-chart-axis-label"
        text-anchor="end"
      >{{ tick }}</text>
      <line
        :x1="padding.left"
        :x2="width - padding.right"
        :y1="height - padding.bottom"
        :y2="height - padding.bottom"
        class="usage-chart-baseline"
      />

      <g v-for="(b, i) in buckets" :key="i">
        <rect
          v-if="b.allowed > 0"
          :x="barX(i)"
          :y="yScale(b.allowed)"
          :width="barWidth"
          :height="Math.max(0, yScale(0) - yScale(b.allowed))"
          rx="2"
          class="usage-chart-bar usage-chart-bar-allowed"
        />
        <rect
          v-if="b.denied > 0"
          :x="barX(i)"
          :y="yScale(b.allowed + b.denied)"
          :width="barWidth"
          :height="Math.max(0, deniedBottom(b) - yScale(b.allowed + b.denied))"
          rx="2"
          class="usage-chart-bar usage-chart-bar-denied"
        />
        <rect
          :x="barX(i)"
          :y="padding.top"
          :width="barWidth"
          :height="height - padding.top - padding.bottom"
          class="usage-chart-hit"
          @pointerenter="hoverIndex = i"
          @pointerleave="hoverIndex === i && (hoverIndex = null)"
          @focus="hoverIndex = i"
          @blur="hoverIndex === i && (hoverIndex = null)"
          tabindex="0"
        />
        <text
          v-if="showXLabel(i)"
          :x="barX(i) + barWidth / 2"
          :y="height - padding.bottom + 16"
          class="usage-chart-axis-label"
          text-anchor="middle"
        >{{ formatLabel(b.label) }}</text>
      </g>
    </svg>

    <div v-if="hoverIndex !== null" class="usage-chart-tooltip">
      <div class="usage-chart-tooltip-title">{{ formatLabel(buckets[hoverIndex].label, true) }}</div>
      <div class="usage-chart-tooltip-row">
        <span class="usage-chart-tooltip-key usage-chart-tooltip-key-allowed"></span>
        Consentiti <strong class="ms-auto">{{ buckets[hoverIndex].allowed }}</strong>
      </div>
      <div class="usage-chart-tooltip-row">
        <span class="usage-chart-tooltip-key usage-chart-tooltip-key-denied"></span>
        Negati <strong class="ms-auto">{{ buckets[hoverIndex].denied }}</strong>
      </div>
      <div class="usage-chart-tooltip-row usage-chart-tooltip-total">
        Totale <strong class="ms-auto">{{ buckets[hoverIndex].total }}</strong>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  title: { type: String, required: true },
  buckets: { type: Array, required: true },
  formatLabel: { type: Function, required: true },
  labelEvery: { type: Number, default: 1 },
})

const hoverIndex = ref(null)

const width = 720
const height = 220
const padding = { top: 12, right: 8, bottom: 26, left: 32 }
const gap = 2

const hasData = computed(() => props.buckets.length > 0)

const maxTotal = computed(() => {
  const max = Math.max(1, ...props.buckets.map((b) => b.total))
  return niceMax(max)
})

function niceMax(value) {
  if (value <= 5) return 5
  const magnitude = Math.pow(10, Math.floor(Math.log10(value)))
  const normalized = value / magnitude
  let niceNormalized
  if (normalized <= 1) niceNormalized = 1
  else if (normalized <= 2) niceNormalized = 2
  else if (normalized <= 5) niceNormalized = 5
  else niceNormalized = 10
  return niceNormalized * magnitude
}

const yTicks = computed(() => {
  const max = maxTotal.value
  return [0, max / 2, max].map((v) => Math.round(v))
})

function yScale(value) {
  const usable = height - padding.top - padding.bottom
  return height - padding.bottom - (value / maxTotal.value) * usable
}

const barSlot = computed(() => (width - padding.left - padding.right) / props.buckets.length)
const barWidth = computed(() => Math.max(2, Math.min(24, barSlot.value - gap)))

function deniedBottom(bucket) {
  return bucket.allowed > 0 ? yScale(bucket.allowed) - gap : yScale(0)
}

function barX(i) {
  return padding.left + i * barSlot.value + (barSlot.value - barWidth.value) / 2
}

function showXLabel(i) {
  return i % props.labelEvery === 0
}
</script>

<style scoped>
.usage-chart {
  position: relative;
  background: #fcfcfb;
  border: 1px solid rgba(11, 11, 11, 0.1);
  border-radius: 6px;
  padding: 12px 16px 8px;
}

.usage-chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.usage-chart-title {
  margin: 0;
  color: #0b0b0b;
  font-weight: 600;
}

.usage-chart-legend {
  display: flex;
  gap: 12px;
  font-size: 0.8rem;
  color: #52514e;
}

.usage-chart-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.usage-chart-swatch {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  display: inline-block;
}

.usage-chart-swatch-allowed {
  background: #0ca30c;
}

.usage-chart-swatch-denied {
  background: #d03b3b;
}

.usage-chart-svg {
  width: 100%;
  height: 220px;
  display: block;
}

.usage-chart-gridline {
  stroke: #e1e0d9;
  stroke-width: 1;
}

.usage-chart-baseline {
  stroke: #c3c2b7;
  stroke-width: 1;
}

.usage-chart-axis-label {
  fill: #898781;
  font-size: 10px;
}

.usage-chart-bar-allowed {
  fill: #0ca30c;
}

.usage-chart-bar-denied {
  fill: #d03b3b;
}

.usage-chart-hit {
  fill: transparent;
  cursor: pointer;
}

.usage-chart-tooltip {
  position: absolute;
  top: 12px;
  right: 16px;
  background: #ffffff;
  border: 1px solid rgba(11, 11, 11, 0.1);
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 0.8rem;
  box-shadow: 0 2px 8px rgba(11, 11, 11, 0.12);
  min-width: 150px;
  pointer-events: none;
}

.usage-chart-tooltip-title {
  font-weight: 600;
  color: #0b0b0b;
  margin-bottom: 4px;
}

.usage-chart-tooltip-row {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #52514e;
}

.usage-chart-tooltip-total {
  border-top: 1px solid #e1e0d9;
  margin-top: 4px;
  padding-top: 4px;
  color: #0b0b0b;
}

.usage-chart-tooltip-key {
  width: 8px;
  height: 2px;
  border-radius: 1px;
  display: inline-block;
}

.usage-chart-tooltip-key-allowed {
  background: #0ca30c;
}

.usage-chart-tooltip-key-denied {
  background: #d03b3b;
}
</style>
