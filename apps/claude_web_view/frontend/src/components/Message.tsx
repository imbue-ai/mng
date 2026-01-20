import { Box, Flex, Text } from "@radix-ui/themes";

import type { ContentBlock, ParsedMessage, TextBlock, ToolResultBlock, ToolUseBlock } from "~/types";
import { isTextBlock, isToolResultBlock, isToolUseBlock } from "~/types";

import { CollapsibleToolSection } from "./CollapsibleToolSection";
import { MarkdownBlock } from "./MarkdownBlock";
import styles from "./Message.module.scss";

interface MessageProps {
  message: ParsedMessage;
  isStreaming?: boolean;
}

type RenderGroup = { type: "text"; blocks: TextBlock[] } | { type: "tools"; blocks: (ToolUseBlock | ToolResultBlock)[] };

export const Message = ({ message, isStreaming = false }: MessageProps) => {
  if (message.role === "user") {
    return <UserMessage message={message} />;
  }
  return <AssistantMessage message={message} isStreaming={isStreaming} />;
};

const UserMessage = ({ message }: { message: ParsedMessage }) => {
  // Extract text content from user message
  const textContent = message.content
    .filter(isTextBlock)
    .map((b) => b.text)
    .join("");

  // Don't render if it's just tool results (no actual user text)
  if (!textContent) {
    return null;
  }

  return (
    <Box className={styles.userMessageWrapper}>
      <Box className={styles.userMessage} px="4" py="3">
        <Text>{textContent}</Text>
      </Box>
    </Box>
  );
};

interface AssistantMessageProps {
  message: ParsedMessage;
  isStreaming: boolean;
}

const AssistantMessage = ({ message, isStreaming }: AssistantMessageProps) => {
  // Group content blocks into render groups
  const renderGroups = groupContentBlocks(message.content);

  if (renderGroups.length === 0) {
    return null;
  }

  return (
    <Box className={styles.assistantMessage} px="4">
      <Flex direction="column" className={styles.assistantMessageContent}>
        {renderGroups.map((group, index) => {
          if (group.type === "text") {
            const mergedText = group.blocks.map((b) => b.text).join("");
            return <MarkdownBlock key={`text-${index}`} content={mergedText} />;
          }
          const isLastGroup = index === renderGroups.length - 1;
          return (
            <CollapsibleToolSection
              key={`tools-${index}`}
              toolBlocks={group.blocks}
              isActive={isStreaming && isLastGroup}
            />
          );
        })}
      </Flex>
    </Box>
  );
};

/**
 * Group consecutive content blocks by type for rendering.
 * Text blocks are merged together, tool blocks are grouped together.
 */
function groupContentBlocks(blocks: ContentBlock[]): RenderGroup[] {
  const groups: RenderGroup[] = [];
  let currentTextBlocks: TextBlock[] = [];
  let currentToolBlocks: (ToolUseBlock | ToolResultBlock)[] = [];

  const flushGroups = () => {
    if (currentTextBlocks.length > 0) {
      groups.push({ type: "text", blocks: currentTextBlocks });
      currentTextBlocks = [];
    }
    if (currentToolBlocks.length > 0) {
      groups.push({ type: "tools", blocks: currentToolBlocks });
      currentToolBlocks = [];
    }
  };

  for (const block of blocks) {
    if (isTextBlock(block)) {
      // Flush tool blocks when switching to text
      if (currentToolBlocks.length > 0) {
        groups.push({ type: "tools", blocks: currentToolBlocks });
        currentToolBlocks = [];
      }
      currentTextBlocks.push(block);
    } else if (isToolUseBlock(block) || isToolResultBlock(block)) {
      // Flush text blocks when switching to tools
      if (currentTextBlocks.length > 0) {
        groups.push({ type: "text", blocks: currentTextBlocks });
        currentTextBlocks = [];
      }
      currentToolBlocks.push(block);
    }
  }

  flushGroups();
  return groups;
}
