import React from "react";

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  padding?: string;
}

export default function Card({
  children,
  padding = "p-6",
  className,
  ...rest
}: CardProps) {
  return (
    <div className={`card-surface ${padding} ${className ?? ""}`} {...rest}>
      {children}
    </div>
  );
}
