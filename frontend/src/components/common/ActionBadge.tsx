type Priority = "urgent" | "review" | "watch";

const STYLES: Record<Priority, string> = {
  urgent: "bg-danger/15 text-danger",
  review: "bg-caution/15 text-caution",
  watch: "bg-positive/15 text-positive",
};

interface ActionBadgeProps {
  priority: Priority;
}

export default function ActionBadge({ priority }: ActionBadgeProps) {
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${STYLES[priority]}`}>
      {priority}
    </span>
  );
}
