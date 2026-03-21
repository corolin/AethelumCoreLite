export interface LLMChatResponse {
  choices?: Array<{ message?: { content?: string } }>;
  content?: string;
}

export interface LLMChatOptions {
  maxTokens?: number;
  temperature?: number;
}

export interface LLMProvider {
  chat(messages: Array<{ role: string; content: string }>, options?: LLMChatOptions): Promise<LLMChatResponse>;
}
