import { Badge, Box, Code, Flex, IconButton, Text } from "@radix-ui/themes";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";

import type { ToolResultBlock, ToolUseBlock } from "~/types";

import styles from "./CollapsibleToolSection.module.scss";

interface CollapsibleToolSectionProps {
  toolBlocks: (ToolUseBlock | ToolResultBlock)[];
  isActive?: boolean;
}

// Tool name display for in-progress/present tense actions
const TOOL_DISPLAY_NAMES_PRESENT: Record<string, string> = {
  Bash: "Running command",
  Read: "Reading file",
  Write: "Writing file",
  Edit: "Editing file",
  MultiEdit: "Editing files",
  Glob: "Searching files",
  Grep: "Searching content",
  LS: "Listing directory",
  WebFetch: "Fetching URL",
  WebSearch: "Searching web",
  TodoRead: "Reading todos",
  TodoWrite: "Updating todos",
  Task: "Running task",
  LSP: "LSP operation",
  NotebookRead: "Reading notebook",
  NotebookEdit: "Editing notebook",
};

function getToolDisplayNamePresent(name: string): string {
  return TOOL_DISPLAY_NAMES_PRESENT[name] || name;
}

function getInvocationString(block: ToolUseBlock): string {
  const input = block.input;
  const name = block.name;

  if (name === "Bash" && input.command) {
    return String(input.command).slice(0, 80);
  }
  if ((name === "Read" || name === "Write" || name === "Edit") && input.file_path) {
    return String(input.file_path);
  }
  if ((name === "Grep" || name === "Glob") && input.pattern) {
    const pattern = String(input.pattern);
    const path = input.path ? ` in ${input.path}` : "";
    return `"${pattern}"${path}`;
  }
  if (name === "WebFetch" && input.url) {
    return String(input.url).slice(0, 60);
  }
  if (name === "WebSearch" && input.query) {
    return String(input.query);
  }
  if (name === "Task" && input.description) {
    return String(input.description);
  }

  const firstStringValue = Object.values(input).find((v) => typeof v === "string" && v);
  return firstStringValue ? String(firstStringValue).slice(0, 60) : "";
}

export const CollapsibleToolSection = ({ toolBlocks, isActive = false }: CollapsibleToolSectionProps) => {
  const [isExpanded, setIsExpanded] = useState(false);

  // For single tool block, render it directly
  if (toolBlocks.length === 1) {
    return <ToolDisplay toolBlock={toolBlocks[0]} />;
  }

  // Get current tool being processed (tool_use without matching result yet)
  const currentTool = isActive ? toolBlocks.find((block) => block.type === "tool_use") : null;
  const currentToolName =
    currentTool && currentTool.type === "tool_use" ? getToolDisplayNamePresent(currentTool.name) : null;

  // For multiple tools, show nested collapsible with "Called Tools" parent
  return (
    <Box className={styles.toolSectionContainer}>
      <Flex
        align="center"
        gap="2"
        py="1"
        px="1"
        className={styles.collapsibleHeader}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <IconButton variant="ghost" size="1" className={styles.chevronIcon}>
          {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </IconButton>
        <Badge className={styles.toolCountBadge}>{toolBlocks.length}</Badge>
        <Text size="2">{isActive ? "Calling Tools" : "Called Tools"}</Text>
        {isActive && currentToolName && !isExpanded && (
          <Text size="1" className={`${styles.ghostText} ${styles.currentToolName}`}>
            {currentToolName}
          </Text>
        )}
      </Flex>

      {isExpanded && (
        <Box ml="5" className={styles.toolsContainer}>
          {toolBlocks.map((block, index) => (
            <ToolDisplay key={index} toolBlock={block} />
          ))}
        </Box>
      )}
    </Box>
  );
};

interface ToolDisplayProps {
  toolBlock: ToolUseBlock | ToolResultBlock;
}

const ToolDisplay = ({ toolBlock }: ToolDisplayProps) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const isToolResult = toolBlock.type === "tool_result";

  // For tool_result, we need to find the tool name from elsewhere or use a default
  // In our simplified model, tool_result doesn't have toolName, so we show generic text
  let displayName: string;
  let collapsedText: string | null = null;

  if (isToolResult) {
    displayName = toolBlock.is_error ? "Error" : "Result";
    collapsedText = toolBlock.content.slice(0, 60);
  } else {
    displayName = getToolDisplayNamePresent(toolBlock.name);
    collapsedText = getInvocationString(toolBlock);
  }

  return (
    <Box>
      <Flex
        align="center"
        gap="2"
        py="1"
        px="1"
        className={styles.toolHeader}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <IconButton variant="ghost" size="1" className={styles.chevronIcon}>
          {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </IconButton>
        <Text size="2" className={styles.toolDisplayName}>
          {displayName}
        </Text>
        {!isExpanded && collapsedText && (
          <Text size="1" className={styles.ghostText}>
            {collapsedText}
          </Text>
        )}
      </Flex>

      {isExpanded && (
        <Box ml="4" mb="2">
          {isToolResult ? (
            <Box className={`${styles.toolResult} ${toolBlock.is_error ? styles.error : styles.success}`}>
              {toolBlock.content}
            </Box>
          ) : (
            <Code size="1" className={styles.toolInput}>
              {JSON.stringify(toolBlock.input, null, 2)}
            </Code>
          )}
        </Box>
      )}
    </Box>
  );
};
