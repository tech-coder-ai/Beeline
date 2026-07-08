import { Component, computed, inject, input } from '@angular/core';
import { NgxEchartsDirective } from 'ngx-echarts';
import type { EChartsCoreOption } from 'echarts/core';
import { ChartSpec } from '../core/models';
import { ThemeService } from '../core/theme.service';

/** Renders a backend ChartSpec with Apache ECharts. */
@Component({
  selector: 'bl-chart',
  imports: [NgxEchartsDirective],
  template: `
    <div class="chart-wrap">
      @if (spec().title) {
        <div class="chart-title">{{ spec().title }}</div>
      }
      <div echarts [options]="options()" class="chart-canvas"></div>
    </div>
  `,
  styles: [`
    .chart-wrap { width: 100%; }
    .chart-title {
      font-size: 13px; font-weight: 600; margin-bottom: 4px;
      color: var(--bl-text-muted);
    }
    .chart-canvas { height: 320px; width: 100%; }
  `],
})
export class ChartComponent {
  readonly spec = input.required<ChartSpec>();
  private theme = inject(ThemeService);

  private palette = [
    '#2f6fed', '#7c5cff', '#12b5a4', '#e2a13b', '#d64545',
    '#3ecf8e', '#5b8def', '#c65cff', '#f57f4f', '#4fc3f7',
  ];

  readonly options = computed<EChartsCoreOption>(() => {
    const spec = this.spec();
    const dark = this.theme.dark();
    const text = dark ? '#93a0b8' : '#5b667a';
    const axisLine = dark ? 'rgba(255,255,255,0.09)' : 'rgba(20,30,60,0.1)';

    const base: EChartsCoreOption = {
      color: this.palette,
      backgroundColor: 'transparent',
      textStyle: { color: text, fontFamily: 'Inter' },
      tooltip: { trigger: spec.chart_type === 'scatter' ? 'item' : 'axis' },
      grid: { left: 48, right: 20, top: 32, bottom: 42, containLabel: true },
      legend:
        spec.series.length > 1
          ? { top: 0, textStyle: { color: text }, icon: 'roundRect' }
          : undefined,
    };

    switch (spec.chart_type) {
      case 'pie':
      case 'donut':
        return {
          ...base,
          tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
          legend: { orient: 'vertical', right: 0, top: 'center', textStyle: { color: text } },
          series: [{
            type: 'pie',
            radius: spec.chart_type === 'donut' ? ['45%', '72%'] : '72%',
            center: ['40%', '52%'],
            data: spec.series[0]?.data ?? [],
            label: { color: text },
            itemStyle: { borderRadius: 6, borderColor: 'transparent', borderWidth: 2 },
          }],
        };

      case 'scatter':
        return {
          ...base,
          xAxis: {
            type: 'value', name: spec.x_label ?? '',
            axisLine: { lineStyle: { color: axisLine } },
            splitLine: { lineStyle: { color: axisLine } },
          },
          yAxis: {
            type: 'value', name: spec.y_label ?? '',
            axisLine: { lineStyle: { color: axisLine } },
            splitLine: { lineStyle: { color: axisLine } },
          },
          series: spec.series.map((s) => ({
            name: s.name, type: 'scatter', data: s.data, symbolSize: 9,
            itemStyle: { opacity: 0.75 },
          })),
        };

      case 'heatmap': {
        const values = (spec.series[0]?.data as [number, number, number][]) ?? [];
        const max = Math.max(...values.map((v) => v[2] ?? 0), 1);
        const yCats = [...new Set(values.map((v) => v[1]))];
        return {
          ...base,
          tooltip: { position: 'top' },
          grid: { left: 90, right: 60, top: 16, bottom: 60 },
          xAxis: { type: 'category', data: spec.categories, axisLine: { lineStyle: { color: axisLine } } },
          yAxis: { type: 'category', data: yCats, axisLine: { lineStyle: { color: axisLine } } },
          visualMap: {
            min: 0, max, calculable: true, orient: 'vertical', right: 0, top: 'center',
            inRange: { color: dark ? ['#1a2b57', '#6f9bff'] : ['#e8efff', '#2f6fed'] },
            textStyle: { color: text },
          },
          series: [{ type: 'heatmap', data: values, label: { show: values.length < 60, color: text } }],
        };
      }

      case 'treemap':
        return {
          ...base,
          series: [{
            type: 'treemap',
            data: spec.series[0]?.data ?? [],
            breadcrumb: { show: false },
            label: { color: '#fff' },
          }],
        };

      default: {
        // line | area | bar
        const isBar = spec.chart_type === 'bar';
        const isArea = spec.chart_type === 'area';
        const horizontal = isBar && (spec.categories?.length ?? 0) > 12;
        const catAxis = {
          type: 'category' as const,
          data: spec.categories,
          axisLine: { lineStyle: { color: axisLine } },
          axisLabel: { color: text, hideOverlap: true, rotate: !horizontal && (spec.categories?.length ?? 0) > 8 ? 35 : 0 },
        };
        const valAxis = {
          type: 'value' as const,
          axisLine: { lineStyle: { color: axisLine } },
          splitLine: { lineStyle: { color: axisLine } },
          axisLabel: { color: text },
        };
        return {
          ...base,
          xAxis: horizontal ? valAxis : catAxis,
          yAxis: horizontal ? catAxis : valAxis,
          series: spec.series.map((s) => ({
            name: s.name,
            type: isBar ? 'bar' : 'line',
            data: s.data,
            smooth: !isBar,
            stack: spec.stacked ? 'total' : undefined,
            areaStyle: isArea ? { opacity: 0.25 } : undefined,
            barMaxWidth: 34,
            itemStyle: isBar ? { borderRadius: [4, 4, 0, 0] } : undefined,
            emphasis: { focus: 'series' },
          })),
        };
      }
    }
  });
}
