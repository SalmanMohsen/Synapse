FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files first — Docker cache means npm ci only re-runs
# when package.json or package-lock.json actually changes
COPY package*.json ./
RUN npm ci

# No COPY . . here — in dev the volume mount provides the source code.
# In production (docker build --target production) the next stage handles it.

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host"]