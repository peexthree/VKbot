## 2025-05-22 - [Hardcoded Backdoor & Referral Exploit]
**Vulnerability:** A hardcoded "god mode" command (`ЛАЙН ГОЛОС`) allowed any user to gain full premium access and reset their state. Additionally, the referral system lacked a "used" check, allowing infinite balance inflation.
**Learning:** Legacy debug commands and incomplete economic logic can bypass all monetization and access controls.
**Prevention:** Always implement explicit identity checks for administrative commands and persistent state flags for one-time bonuses.
