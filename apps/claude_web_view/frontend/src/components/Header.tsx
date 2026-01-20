import { Badge, Flex, Text } from "@radix-ui/themes";

import type { SessionMetadata } from "~/types";

import styles from "./Header.module.scss";

interface HeaderProps {
  metadata: SessionMetadata | null;
  isConnected: boolean;
}

export const Header = ({ metadata, isConnected }: HeaderProps) => {
  return (
    <Flex className={styles.header} align="center" justify="between" px="4" py="2">
      <Flex align="center" gap="3">
        <Text weight="bold" size="3">
          ClaudeWebView
        </Text>
        {metadata && (
          <Text size="2" color="gray">
            {metadata.model}
          </Text>
        )}
      </Flex>
      <Badge color={isConnected ? "green" : "red"} variant="soft">
        {isConnected ? "Connected" : "Disconnected"}
      </Badge>
    </Flex>
  );
};
