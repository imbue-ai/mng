import { Box, Flex, IconButton, ScrollArea, Tooltip } from "@radix-ui/themes";
import { ArrowRightIcon, ImageIcon, X } from "lucide-react";
import { useCallback, useRef, useState } from "react";

import styles from "./ChatInput.module.scss";

interface ChatInputProps {
  disabled?: boolean;
}

/** Convert a File to base64 data URL */
const fileToBase64 = (file: File): Promise<string> => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
};

export const ChatInput = ({ disabled = false }: ChatInputProps) => {
  const [message, setMessage] = useState("");
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const [isSending, setIsSending] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSend = useCallback(async () => {
    if (!message.trim() && attachedFiles.length === 0) return;
    if (disabled || isSending) return;

    setIsSending(true);
    try {
      // Convert files to base64
      const fileData = await Promise.all(attachedFiles.map(fileToBase64));

      // Send to backend
      const response = await fetch("/api/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: message.trim(),
          files: fileData,
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to send: ${response.statusText}`);
      }

      // Clear input on success
      setMessage("");
      setAttachedFiles([]);

      // Reset textarea height
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
      }
    } catch (error) {
      console.error("Failed to send message:", error);
    } finally {
      setIsSending(false);
    }
  }, [message, attachedFiles, disabled, isSending]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Send on Enter (without shift)
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;

    const imageFiles = Array.from(files).filter((f) => f.type.startsWith("image/"));
    setAttachedFiles((prev) => [...prev, ...imageFiles]);

    // Reset input so same file can be selected again
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const removeFile = (index: number) => {
    setAttachedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setMessage(e.target.value);

    // Auto-resize textarea
    const textarea = e.target;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 300)}px`;
  };

  return (
    <div className={styles.container}>
      <Flex direction="column" gapY="3" className={styles.inputSection}>
        {/* Editor wrapper with border - matches Sculptor's Editor component */}
        <div className={`${styles.editorWrapper} ${disabled ? styles.disabled : ""}`}>
          <ScrollArea scrollbars="vertical" style={{ maxHeight: 300, height: "auto" }}>
            <textarea
              ref={textareaRef}
              className={styles.editor}
              placeholder="Type a message..."
              value={message}
              onChange={handleTextareaChange}
              onKeyDown={handleKeyDown}
              disabled={disabled}
              rows={1}
            />
          </ScrollArea>
          {/* Attached files preview inside editor wrapper like Sculptor's footer */}
          {attachedFiles.length > 0 && (
            <div className={styles.footer}>
              <Flex gap="2" wrap="wrap">
                {attachedFiles.map((file, index) => (
                  <Box key={index} className={styles.filePreview}>
                    <img
                      src={URL.createObjectURL(file)}
                      alt={file.name}
                      className={styles.previewImage}
                    />
                    <IconButton
                      size="1"
                      variant="ghost"
                      className={styles.removeFileButton}
                      onClick={() => removeFile(index)}
                    >
                      <X size={12} />
                    </IconButton>
                  </Box>
                ))}
              </Flex>
            </div>
          )}
        </div>

        {/* Action buttons row - outside the bordered editor */}
        <Flex align="center" justify="between" gapX="4" direction="row" className={styles.actionButtons}>
          <div> </div>
          <Flex align="center" gapX="3">
            {/* Attach images button */}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              onChange={handleFileSelect}
              style={{ display: "none" }}
            />
            <Tooltip content="Attach images">
              <IconButton
                variant="ghost"
                onClick={() => fileInputRef.current?.click()}
                disabled={disabled}
                className={styles.attachButton}
              >
                <ImageIcon size={16} />
              </IconButton>
            </Tooltip>

            {/* Send button */}
            <IconButton
              onClick={handleSend}
              disabled={disabled || isSending}
              className={styles.sendButton}
            >
              <ArrowRightIcon size={16} />
            </IconButton>
          </Flex>
        </Flex>
      </Flex>
    </div>
  );
};
