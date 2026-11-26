import { createContext, useCallback, useContext, useRef, useState, type PropsWithChildren } from "react";
import { Toast } from "../../components/primitives/Toast";

interface Notice {
  message: string;
  requestId?: string;
}

const ToastContext = createContext<((notice: Notice) => void) | null>(null);

export function ToastProvider({ children }: PropsWithChildren) {
  const nextId = useRef(0);
  const [notices, setNotices] = useState<(Notice & { id: number })[]>([]);
  const show = useCallback((notice: Notice) => {
    const id = nextId.current++;
    setNotices((current) => [...current, { ...notice, id }]);
  }, []);

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className="toasts">
        {notices.map(({ id, message, requestId }) => (
          <Toast key={id} message={message} requestId={requestId}
            onDismiss={() => setNotices((current) => current.filter((notice) => notice.id !== id))} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const show = useContext(ToastContext);
  if (!show) throw new Error("ToastProvider is missing");
  return show;
}
