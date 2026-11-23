import type { TFunction } from "i18next";

const defaultConfig = {
  theme: {
    // The upstream chat theme generator parses this value as a HEX color.
    // Runtime theme colors are normalized before they are passed to it.
    colorPrimary: "#1668DC",
    darkMode: false,
    prefix: "qwenpaw",
    leftHeader: {
      logo: "",
      title: "Work with 小蜜蜂",
    },
    bubbleList: {
      userMessageAnchors: {
        variant: "navigator",
      },
    },
  },
  sender: {
    attachments: true,
    // The host handles long pastes without replacing or truncating drafts.
    longTextUpload: false,
    disclaimer: "Works for you, grows with you",
  },
  welcome: {
    greeting:
      "Which bank reputation or public-opinion matter should we handle today?",
    description:
      "A reputation-risk assistant for banks and financial institutions.",
    avatar: `${import.meta.env.BASE_URL}online.svg`,
    prompts: [
      {
        value:
          "Assess the risk level and response options for this bank-related negative coverage",
      },
      {
        value:
          "Draft external talking points for a customer-complaint reputation issue",
      },
      {
        value:
          "Write multi-role online comment scripts to cool down public opinion",
      },
      {
        value:
          "Using the “Public opinion assessment” skill as a reference, create a personal Skill for fast branch-complaint response that I can iterate on later",
      },
    ],
  },
  api: {
    baseURL: "",
    token: "",
  },
} as const;

class ChatConfigProvider {
  getGreeting(t: TFunction): string {
    return t("chat.greeting");
  }

  getDescription(t: TFunction): string {
    return t("chat.description");
  }

  getPrompts(t: TFunction): Array<{ value: string }> {
    return [
      { value: t("chat.prompt1") },
      { value: t("chat.prompt2") },
      { value: t("chat.prompt3") },
      { value: t("chat.prompt4") },
    ];
  }

  getConfig(t: TFunction) {
    return {
      ...defaultConfig,
      sender: {
        ...defaultConfig.sender,
        disclaimer: t("chat.disclaimer"),
      },
      welcome: {
        ...defaultConfig.welcome,
        greeting: this.getGreeting(t),
        description: this.getDescription(t),
        prompts: this.getPrompts(t),
      },
    };
  }
}

const configProvider = new ChatConfigProvider();

export function getDefaultConfig(t: TFunction) {
  return configProvider.getConfig(t);
}

export default defaultConfig;

export type DefaultConfig = typeof defaultConfig;

// Export provider for extension
export { configProvider };
