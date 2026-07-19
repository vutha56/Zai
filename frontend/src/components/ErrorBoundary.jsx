import React from "react";

// Contain component crashes so a single broken widget (e.g. the chart) can
// never blank the whole page. Renders a quiet fallback instead.
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    console.error("ErrorBoundary caught:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback || (
          <div
            style={{
              padding: "24px",
              color: "var(--color-ink-muted-48)",
              fontSize: "14px",
              textAlign: "center",
            }}
          >
            This section couldn’t be displayed.
          </div>
        )
      );
    }
    return this.props.children;
  }
}
