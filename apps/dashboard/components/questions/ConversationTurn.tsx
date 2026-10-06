import { Badge } from "@/components/ui";
import { formatDate } from "@/utils/formatters";
import type { TurnDetail } from "@/utils/types";

interface ConversationTurnProps {
  turn: TurnDetail;
}

function getConfidenceVariant(
  confidence: number,
): "success" | "warning" | "error" {
  if (confidence >= 0.8) return "success";
  if (confidence >= 0.5) return "warning";
  return "error";
}

function getInterpretationVariant(
  interpretation: string,
): "info" | "purple" | "default" {
  switch (interpretation.toLowerCase()) {
    case "answer":
      return "info";
    case "user_question":
      return "purple";
    default:
      return "default";
  }
}

function AssistantMessage({
  message,
  timestamp,
}: {
  message: string;
  timestamp?: string;
}) {
  return (
    <div className="flex items-start">
      <div className="shrink-0 w-8 h-8 rounded-full bg-brand flex items-center justify-center text-white text-xs font-bold">
        AI
      </div>
      <div className="ml-3 flex-1">
        <div className="bg-brand/5 rounded-lg p-4 border border-brand/10">
          <p className="text-gray-900">{message}</p>
        </div>
        <div className="text-xs text-gray-400 mt-1">
          {formatDate(timestamp)}
        </div>
      </div>
    </div>
  );
}

function UserMessageBadges({ turn }: { turn: TurnDetail }) {
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {turn.llm_interpretation && (
        <Badge variant={getInterpretationVariant(turn.llm_interpretation)}>
          {turn.llm_interpretation}
        </Badge>
      )}

      {turn.llm_confidence !== null && (
        <Badge variant={getConfidenceVariant(turn.llm_confidence)}>
          {(turn.llm_confidence * 100).toFixed(0)}% confidence
        </Badge>
      )}

      {turn.escalated && <Badge variant="error">🚨 Escalated</Badge>}

      {turn.validation_result && (
        <Badge variant={turn.validation_result.valid ? "success" : "error"}>
          {turn.validation_result.valid ? "✓ Valid" : "✗ Invalid"}
          {turn.validation_result.reason &&
            `: ${turn.validation_result.reason}`}
        </Badge>
      )}
    </div>
  );
}

function UserMessage({ turn }: { turn: TurnDetail }) {
  return (
    <div className="flex items-start justify-end">
      <div className="mr-3 flex-1 text-right">
        <div className="bg-gray-100 rounded-lg p-4 border border-gray-200 inline-block text-left max-w-xl">
          <p className="text-gray-900">{turn.user_message}</p>
          <UserMessageBadges turn={turn} />
        </div>
      </div>
      <div className="shrink-0 w-8 h-8 rounded-full bg-gray-500 flex items-center justify-center text-white text-xs font-bold">
        U
      </div>
    </div>
  );
}

export default function ConversationTurn({ turn }: ConversationTurnProps) {
  return (
    <div className="space-y-3">
      {turn?.assistant_message && (
        <AssistantMessage
          message={turn.assistant_message}
          timestamp={turn?.timestamp}
        />
      )}

      {turn?.user_message && <UserMessage turn={turn} />}
    </div>
  );
}
