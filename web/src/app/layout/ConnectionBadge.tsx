import { Badge } from "../../components/primitives/Badge";
import { useAuth } from "../providers/AuthProvider";
import { useStream } from "../providers/StreamProvider";

export function ConnectionBadge() {
  const { identityError } = useAuth();
  const { stale } = useStream();
  return (
    <span role="status">
      {identityError ? <Badge tone="warning">Ошибка API</Badge> :
        stale ? <Badge tone="warning">Данные устарели</Badge> :
          <Badge tone="success">API доступен</Badge>}
    </span>
  );
}
