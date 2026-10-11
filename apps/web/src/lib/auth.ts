import { AuthenticationDetails, CognitoUser, CognitoUserPool } from "amazon-cognito-identity-js";
import { config } from "./config";
import { clearSession, sessionFromIdToken, setSession, type Session } from "./session";

let pool: CognitoUserPool | null = null;

function getPool(): CognitoUserPool {
  if (!pool) {
    // Tokens live in our own session store, so give the SDK a throwaway storage.
    const mem: Record<string, string> = {};
    pool = new CognitoUserPool({
      UserPoolId: config.userPoolId,
      ClientId: config.clientId,
      Storage: {
        setItem: (k: string, v: string) => (mem[k] = v),
        getItem: (k: string) => mem[k] ?? null,
        removeItem: (k: string) => delete mem[k],
        clear: () => Object.keys(mem).forEach((k) => delete mem[k]),
      },
    });
  }
  return pool;
}

let activeUser: CognitoUser | null = null;

export function signIn(email: string, password: string): Promise<Session> {
  const user = new CognitoUser({ Username: email.trim(), Pool: getPool() });
  const details = new AuthenticationDetails({ Username: email.trim(), Password: password });
  return new Promise((resolve, reject) => {
    user.authenticateUser(details, {
      onSuccess: (result) => {
        try {
          const session = sessionFromIdToken(result.getIdToken().getJwtToken());
          activeUser = user;
          setSession(session);
          resolve(session);
        } catch (err) {
          reject(err);
        }
      },
      onFailure: (err: { code?: string; message?: string }) => reject(new Error(authMessage(err))),
      newPasswordRequired: () =>
        reject(new Error("This account needs a new password. Ask an administrator to reset it.")),
    });
  });
}

export function signOut(): void {
  try {
    activeUser?.signOut();
  } catch {
    // tokens are dropped locally either way
  }
  activeUser = null;
  clearSession();
}

function authMessage(err: { code?: string; message?: string }): string {
  switch (err.code) {
    case "NotAuthorizedException":
      return "Incorrect email or password.";
    case "UserNotFoundException":
      return "Incorrect email or password.";
    case "PasswordResetRequiredException":
      return "Password reset required. Contact an administrator.";
    case "TooManyRequestsException":
    case "LimitExceededException":
      return "Too many attempts. Wait a minute and try again.";
    case "NetworkError":
      return "Could not reach the sign-in service. Check your connection.";
    default:
      return err.message ?? "Sign-in failed.";
  }
}
