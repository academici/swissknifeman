import type { MetricGroup } from "../contracts";
import { ViewLinkTo } from "./common";

export function MetricGroupView({ data, projectId }: { data: MetricGroup; projectId?: string }) {
  return (
    <div className="metric-group">
      {data.metrics.map((metric) => (
        <div key={metric.id} className={`metric metric-${metric.status}`}>
          <ViewLinkTo link={metric.link} projectId={projectId}>
            <div className="metric-value">
              {metric.value}
              {metric.unit ? <span className="metric-unit"> {metric.unit}</span> : null}
            </div>
            <div className="metric-label">{metric.label}</div>
          </ViewLinkTo>
        </div>
      ))}
    </div>
  );
}
