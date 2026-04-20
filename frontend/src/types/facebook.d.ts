/**
 * Minimal type declarations for the Meta (Facebook) JS SDK.
 * Used for Embedded Signup flow.
 */

interface FBAuthResponse {
  code?: string;
  accessToken?: string;
  userID?: string;
  expiresIn?: number;
  signedRequest?: string;
  graphDomain?: string;
  data_access_expiration_time?: number;
}

interface FBLoginResponse {
  status: "connected" | "not_authorized" | "unknown";
  authResponse: FBAuthResponse | null;
}

interface FBInitParams {
  appId: string;
  version: string;
  autoLogAppEvents?: boolean;
  xfbml?: boolean;
}

interface FBLoginOptions {
  config_id?: string;
  response_type?: "code" | "token";
  override_default_response_type?: boolean;
  extras?: {
    setup?: Record<string, unknown>;
    featureType?: string;
    sessionInfoVersion?: string;
  };
}

interface FB {
  init(params: FBInitParams): void;
  login(callback: (response: FBLoginResponse) => void, options?: FBLoginOptions): void;
  logout(callback?: (response: unknown) => void): void;
  getLoginStatus(callback: (response: FBLoginResponse) => void): void;
}

declare global {
  interface Window {
    FB: FB;
    fbAsyncInit?: () => void;
  }
}

export {};
