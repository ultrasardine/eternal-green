# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it by creating a private security advisory on GitHub or by opening an issue.

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will respond as quickly as possible and work with you to address the issue.

## Security Considerations

Eternal Green simulates user input using `pyautogui`. Please be aware:

- The application moves the mouse cursor and can send keystrokes
- Use silent mode if you want to avoid keystroke simulation
- Review the configuration before running in production environments
- The application requires appropriate system permissions for input simulation
